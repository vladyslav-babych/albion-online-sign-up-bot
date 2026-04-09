from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord

import globals
import guild_settings


_TIMER_TASK: Optional[asyncio.Task] = None
_TIMER_DISPLAY_INTERVAL_MINUTES = 10


def start_utc_timer_scheduler(bot: discord.Client) -> None:
    global _TIMER_TASK
    if _TIMER_TASK is not None and not _TIMER_TASK.done():
        return
    _TIMER_TASK = bot.loop.create_task(_utc_timer_loop(bot))


async def refresh_utc_timer_channels(bot: discord.Client) -> None:
    await _refresh_all_timer_channels(bot)


async def handle_add_utc_timer_slash(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    me = interaction.guild.me
    if me is None:
        try:
            me = await interaction.guild.fetch_member(interaction.client.user.id)
        except (AttributeError, discord.NotFound, discord.Forbidden, discord.HTTPException):
            me = None

    if me is not None and not me.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "The bot needs the Manage Channels permission to create and update the UTC timer channel.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    existing_channel = await _get_configured_timer_channel(interaction.guild)
    if existing_channel is not None:
        await _ensure_timer_channel_permissions(existing_channel, me)
        await _sync_timer_channel_name(existing_channel)
        await interaction.followup.send(
            f"UTC timer channel is already configured: {existing_channel.mention}",
            ephemeral=True,
        )
        return

    category = interaction.channel.category if interaction.channel is not None else None

    try:
        channel = await interaction.guild.create_voice_channel(
            name=_format_utc_channel_name(),
            category=category,
            overwrites=_build_timer_overwrites(interaction.guild, me),
            reason=f"UTC timer channel requested by {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Missing permission to create the UTC timer voice channel.",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            "Failed to create the UTC timer voice channel due to a Discord API error.",
            ephemeral=True,
        )
        return

    guild_settings.set_utc_timer_channel(interaction.guild.id, channel.id)
    await interaction.followup.send(f"Created UTC timer channel: {channel.mention}", ephemeral=True)


async def _utc_timer_loop(bot: discord.Client) -> None:
    await bot.wait_until_ready()

    while True:
        try:
            await _refresh_all_timer_channels(bot)
        except Exception:
            logging.exception("UTC timer tick failed")
        await asyncio.sleep(_seconds_until_next_minute())


async def _refresh_all_timer_channels(bot: discord.Client) -> None:
    for guild_id, channel_id in guild_settings.get_all_utc_timer_channels().items():
        guild = bot.get_guild(guild_id)
        if guild is None:
            try:
                guild = await bot.fetch_guild(guild_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                guild_settings.clear_utc_timer_channel(guild_id)
                continue

        if not isinstance(channel, discord.VoiceChannel):
            guild_settings.clear_utc_timer_channel(guild_id)
            continue

        await _sync_timer_channel_name(channel)


async def _get_configured_timer_channel(guild: discord.Guild) -> Optional[discord.VoiceChannel]:
    channel_id = guild_settings.get_utc_timer_channel(guild.id)
    if channel_id is None:
        return None

    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            guild_settings.clear_utc_timer_channel(guild.id)
            return None

    if not isinstance(channel, discord.VoiceChannel):
        guild_settings.clear_utc_timer_channel(guild.id)
        return None

    return channel


async def _sync_timer_channel_name(channel: discord.VoiceChannel) -> None:
    expected_name = _format_utc_channel_name()
    if channel.name == expected_name:
        return

    try:
        await channel.edit(name=expected_name, reason="UTC timer update")
    except (discord.Forbidden, discord.HTTPException):
        logging.warning("Failed to update UTC timer channel %s in guild %s", channel.id, channel.guild.id)


async def _ensure_timer_channel_permissions(channel: discord.VoiceChannel, me: Optional[discord.Member]) -> None:
    overwrites = _build_timer_overwrites(channel.guild, me)
    if channel.overwrites == overwrites:
        return

    try:
        await channel.edit(overwrites=overwrites, reason="UTC timer permission sync")
    except (discord.Forbidden, discord.HTTPException):
        logging.warning("Failed to sync UTC timer permissions for channel %s in guild %s", channel.id, channel.guild.id)


def _build_timer_overwrites(guild: discord.Guild, me: Optional[discord.Member]) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(
            connect=False,
            speak=False,
            stream=False,
            use_voice_activation=False,
        ),
    }

    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            connect=False,
        )

    return overwrites


def _format_utc_channel_name() -> str:
    now = datetime.now(timezone.utc)
    rounded_minute = (now.minute // _TIMER_DISPLAY_INTERVAL_MINUTES) * _TIMER_DISPLAY_INTERVAL_MINUTES
    rounded_time = now.replace(minute=rounded_minute, second=0, microsecond=0)
    return rounded_time.strftime("Time UTC: %H:%M")


def _seconds_until_next_minute() -> float:
    now = datetime.now(timezone.utc)
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max((next_minute - now).total_seconds(), 1.0)