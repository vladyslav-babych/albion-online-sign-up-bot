import asyncio
import discord
import albion_client as client
import google_sheets
import guild_settings
from typing import Optional


async def sync_discord_nickname(member: discord.Member, albion_nickname: str):
    try:
        await member.edit(nick=albion_nickname, reason='Sync nickname after registration')
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def add_member_role(member: discord.Member, role_name: str = 'Member'):
    role = discord.utils.get(member.guild.roles, name=role_name)
    await member.add_roles(role, reason=f'Add {role_name} role after registration')


async def _get_player_info_with_retries(nickname: str, target_guild_name: str) -> Optional[dict]:
    target = (target_guild_name or "").strip().casefold()
    query = (nickname or "").strip()
    last: Optional[dict] = None

    delays = (0.0, 1.5, 3.0)
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            await asyncio.sleep(delay)

        try:
            info = await asyncio.to_thread(client.get_player_by_nickname, query)
        except Exception:
            info = None

        if not isinstance(info, dict):
            continue

        last = info
        guild_name = str(info.get('GuildName') or '').strip().casefold()

        if guild_name and guild_name == target:
            return info

        if attempt < len(delays):
            continue

    return last


async def register_user(context, nickname: str, worksheet, target_guild_name: Optional[str]):
    if not target_guild_name:
        await context.send(
            "This server is not configured yet. Ask an admin to run **/bot-setup** first."
        )
        return

    player_info = await _get_player_info_with_retries(nickname, target_guild_name)
    if player_info is None:
        await context.send(f"Player with nickname **{nickname}** was not found.")
        return

    discord_id = context.author.id
    player_name = (player_info.get('Name') or nickname).strip()
    player_guild = (player_info.get('GuildName') or '').strip()

    if player_guild.casefold() != target_guild_name.strip().casefold():
        if player_guild:
            await context.send(
                f"Character **{player_name}** is in **{player_guild}**.\n"
                f"Only **{target_guild_name}** members can register."
            )
            return

        await context.send(
            f"Character **{player_name}** is not in a guild.\n"
            f"Only **{target_guild_name}** members can register."
        )
        return

    exists, conflict_field = google_sheets.registration_exists(worksheet, discord_id, player_name)
    if exists:
        if conflict_field == 'discord_id':
            updated = google_sheets.reactivate_registration(worksheet, discord_id, player_name)
            if updated:
                await sync_discord_nickname(context.author, player_name)
                member_role_name = guild_settings.get_member_role(context.guild.id)
                await add_member_role(context.author, member_role_name)
                await context.send(
                    f"Your registration was updated and **{player_name}** is marked as **in guild** again."
                )
                return

            await context.send("You are already registered.")
            return

        await context.send(f"Character **{player_name}** is already registered.")
        return

    google_sheets.add_user_to_worksheet(worksheet, discord_id, player_name, silver=0)

    await sync_discord_nickname(context.author, player_name)
    member_role_name = guild_settings.get_member_role(context.guild.id)
    await add_member_role(context.author, member_role_name)
    await context.send(f"**{player_name}** was registered successfully.")