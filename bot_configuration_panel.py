import discord
import guild_settings
import google_sheet_credentials_store
from pathlib import Path
from typing import Tuple


def _format_named_role_mentions(guild: discord.Guild, role_names: list[str]) -> str:
    mentions: list[str] = []
    normalized = {role_name.strip().lower() for role_name in role_names if role_name.strip()}
    if not normalized:
        return "Not configured yet"

    for role in guild.roles:
        if role.name.strip().lower() in normalized:
            mentions.append(role.mention)

    return ", ".join(mentions) if mentions else ", ".join(role_names)


def _build_bot_configuration_panel(guild: discord.Guild) -> discord.Embed:
    not_configured = "Not configured yet"
    discord_server_id = guild.id

    guild_name = guild_settings.get_target_guild(discord_server_id) or not_configured
    caller_role_names = guild_settings.get_caller_roles(discord_server_id)
    economy_manager_role_names = guild_settings.get_economy_manager_roles(discord_server_id)
    member_role_name = guild_settings.get_member_role(discord_server_id) or "Member"

    caller_roles = _format_named_role_mentions(guild, caller_role_names)
    economy_manager_roles = _format_named_role_mentions(guild, economy_manager_role_names)
    member_role = _format_named_role_mentions(guild, [member_role_name])
    bot_updates_channel_id = guild_settings.get_bot_updates_channel(discord_server_id)
    bot_updates_channel = f"<#{bot_updates_channel_id}>" if bot_updates_channel_id else not_configured

    creds_info = google_sheet_credentials_store.get_credentials_info(discord_server_id)
    credentials_file = not_configured
    google_sheet_name = not_configured
    players_worksheet_name = not_configured
    lootsplit_history_worksheet_name = not_configured
    balance_history_worksheet_name = not_configured

    if creds_info:
        credentials_path = creds_info.get("credentials_file")
        if credentials_path:
            credentials_file = Path(str(credentials_path)).name

        google_sheet_name = creds_info.get("google_sheet_name") or not_configured
        players_worksheet_name = creds_info.get("google_worksheet_name") or not_configured
        lootsplit_history_worksheet_name = creds_info.get("lootsplit_history_worksheet_name") or not_configured
        balance_history_worksheet_name = creds_info.get("balance_history_worksheet_name") or not_configured

    embed = discord.Embed(
        title="Bot Configuration",
        description="## :gear: Current server setup and Google Sheets configuration",
    )
    embed.add_field(name="Guild name", value=guild_name, inline=False)
    embed.add_field(name="Caller role(s)", value=caller_roles, inline=False)
    embed.add_field(name="Economy Manager role(s)", value=economy_manager_roles, inline=False)
    embed.add_field(name="Member role", value=member_role, inline=False)
    embed.add_field(name="Bot updates channel", value=bot_updates_channel, inline=False)
    embed.add_field(name="Credentials file", value=credentials_file, inline=False)
    embed.add_field(name="Google Sheet name", value=google_sheet_name, inline=False)
    embed.add_field(name="Players Worksheet name", value=players_worksheet_name, inline=False)
    embed.add_field(name="Lootsplit History Worksheet name", value=lootsplit_history_worksheet_name, inline=False)
    embed.add_field(name="Balance History Worksheet name", value=balance_history_worksheet_name, inline=False)
    return embed


async def post_or_update_bot_configuration_message(interaction: discord.Interaction) -> Tuple[bool, str]:
    if interaction.guild is None or interaction.channel is None:
        return False, "Cannot access channel in this context."

    embed = _build_bot_configuration_panel(interaction.guild)
    channel_id, message_id = guild_settings.get_bot_configuration_message(interaction.guild.id)

    if channel_id and message_id:
        try:
            target_channel = interaction.guild.get_channel(channel_id)
            if target_channel is None:
                target_channel = await interaction.guild.fetch_channel(channel_id)

            existing_message = await target_channel.fetch_message(message_id)
            await existing_message.edit(content=None, embed=embed)
            return True, "Bot configuration message updated."
        except discord.NotFound:
            pass
        except discord.Forbidden:
            return False, "Missing permission to edit the existing bot configuration message."
        except discord.HTTPException:
            return False, "Failed to update the existing bot configuration message."

    try:
        new_message = await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        return False, "Missing permission to send messages in this channel."
    except discord.HTTPException:
        return False, "Failed to send bot configuration message."

    guild_settings.set_bot_configuration_message(interaction.guild.id, interaction.channel.id, new_message.id)
    return True, "Bot configuration message posted."
