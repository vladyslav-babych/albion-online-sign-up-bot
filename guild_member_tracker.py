from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord

import albion_client
import google_sheets
import guild_settings


_CHECK_INTERVAL_SECONDS = 300

_tracker_task: Optional[asyncio.Task] = None


def start_guild_member_tracker(bot: discord.Client) -> None:
    global _tracker_task
    if _tracker_task is not None and not _tracker_task.done():
        return
    _tracker_task = bot.loop.create_task(_tracker_loop(bot))


async def _tracker_loop(bot: discord.Client) -> None:
    while True:
        try:
            await _process_all_servers(bot)
        except Exception:
            logging.exception("Guild member tracker tick failed")
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def _process_all_servers(bot: discord.Client) -> None:
    for server_id in guild_settings.get_all_configured_server_ids():
        guild = bot.get_guild(server_id)
        if guild is None:
            continue

        target_guild_name = guild_settings.get_target_guild(server_id)
        if not target_guild_name:
            continue

        leave_action = guild_settings.get_leave_action(server_id)

        try:
            worksheet = await asyncio.to_thread(google_sheets.get_worksheet, server_id)
            await _process_server_with_sheet(bot, guild, target_guild_name, leave_action, worksheet)
        except Exception as err:
            logging.info(
                "Tracker: no sheet linked/available for server %s (%s). Skipping enforcement.",
                server_id,
                err,
            )
            continue


async def _process_server_with_sheet(
    bot: discord.Client,
    guild: discord.Guild,
    target_guild_name: str,
    leave_action: str,
    worksheet,
) -> None:
    try:
        rows = await asyncio.to_thread(worksheet.get_all_values)
    except Exception as err:
        logging.warning("Tracker: failed to read worksheet for server %s: %s", guild.id, err)
        return

    updates: list[tuple[int, str]] = []

    schema_supports_flag = _worksheet_supports_in_guild_flag(rows)

    for row_index, row in enumerate(rows, start=1):
        if not row or len(row) < 2:
            continue

        discord_id_raw = (row[0] or "").strip()
        nickname = (row[1] or "").strip()
        current_flag = (row[2] if len(row) >= 3 else "").strip().upper()

        if not discord_id_raw.isdigit() or not nickname:
            continue

        if current_flag == "NO":
            continue

        discord_id = int(discord_id_raw)

        try:
            profile = await asyncio.to_thread(albion_client.get_player_profile_by_exact_nickname, nickname)
        except Exception:
            profile = None

        if not isinstance(profile, dict):
            continue

        player_guild = (profile.get("GuildName") or "").strip()
        in_guild = player_guild.casefold() == target_guild_name.strip().casefold()

        if in_guild:
            continue

        member = guild.get_member(discord_id)
        if member is None:
            try:
                member = await guild.fetch_member(discord_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None

        if member is not None:
            await _apply_leave_action(bot, guild, member, leave_action)

        if schema_supports_flag:
            updates.append((row_index, "NO"))

    if updates and schema_supports_flag:
        try:
            await asyncio.to_thread(google_sheets.batch_update_in_guild_flags, worksheet, updates)
        except Exception as err:
            logging.warning("Tracker: failed to update in-guild flags for server %s: %s", guild.id, err)


def _worksheet_supports_in_guild_flag(rows: list[list[str]]) -> bool:
    if not rows:
        return True

    header = [str(cell or "").strip().casefold() for cell in (rows[0] or [])]
    if len(header) >= 3 and header[2] in {"is in guild", "is_in_guild", "in guild", "in_guild"}:
        return True

    sample = rows[1:6]
    if sample and all(len(r) <= 3 for r in sample if isinstance(r, list)):
        return False

    return True


async def _apply_leave_action(bot: discord.Client, guild: discord.Guild, member: discord.Member, leave_action: str) -> None:
    action = (leave_action or "").strip().lower()
    reason = f"Albion guild membership audit ({_now_utc()})"

    if action == "none":
        return

    if action == "kick":
        if member.id == guild.owner_id:
            return
        try:
            if member.guild_permissions.administrator:
                return
        except Exception:
            pass
        try:
            await member.kick(reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            return
        return

    await _remove_all_roles(bot, guild, member, reason)


async def _remove_all_roles(bot: discord.Client, guild: discord.Guild, member: discord.Member, reason: str) -> None:
    me = guild.me or guild.get_member(getattr(bot.user, "id", 0))
    if me is None:
        try:
            me = await guild.fetch_member(getattr(bot.user, "id", 0))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            me = None

    bot_top_role = me.top_role if me is not None else None

    roles_to_remove: list[discord.Role] = []
    for role in member.roles:
        if role.is_default():
            continue
        if role.managed:
            continue
        if bot_top_role is not None and role >= bot_top_role:
            continue
        roles_to_remove.append(role)

    if not roles_to_remove:
        return

    try:
        await member.remove_roles(*roles_to_remove, reason=reason)
    except (discord.Forbidden, discord.HTTPException):
        return
