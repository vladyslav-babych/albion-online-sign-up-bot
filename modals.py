import discord
import guild_settings
import globals
import google_sheet_credentials_store
from pathlib import Path
from typing import Tuple


def _apply_server_setup(
    discord_server_id: int,
    target_guild_name: str,
    member_role_name: str = "Member",
    caller_role_name: str = "Caller",
) -> Tuple[bool, str]:
    target_guild_name = target_guild_name.strip()

    existing_guild_name = guild_settings.get_target_guild(discord_server_id)
    if existing_guild_name:
        return False, f"This server is already set up with the **{existing_guild_name}** guild."

    existing_server_id = guild_settings.get_server_id_by_target_guild(target_guild_name)
    if existing_server_id and int(existing_server_id) != discord_server_id:
        return (
            False,
            f"The **{target_guild_name}** guild is already set up by another discord server. \n"
            f"If **{target_guild_name}** is your guild, please contact bot owner directly to resolve this conflict.",
        )

    guild_settings.set_target_guild(discord_server_id, target_guild_name, member_role_name, caller_role_name)
    return (
        True,
        f"Setup saved. Discord server ID **{discord_server_id}** is now mapped to the guild **{target_guild_name}**.",
    )


def _build_bot_configuration_message(discord_server_id: int) -> str:
    not_configured = "Not configured yet"

    guild_name = guild_settings.get_target_guild(discord_server_id) or not_configured
    caller_roles = ", ".join(guild_settings.get_caller_roles(discord_server_id)) or "Caller"
    member_role = guild_settings.get_member_role(discord_server_id) or "Member"

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

    plain_message = (
        "## Bot configuration:\n\n"
        f"**Guild name:** {guild_name}\n\n"
        f"**Caller role(s):** {caller_roles}\n\n"
        f"**Member role:** {member_role}\n\n"
        f"**Credentials file:** {credentials_file}\n\n"
        f"**Google Sheet name:** {google_sheet_name}\n\n"
        f"**Players Worksheet name:** {players_worksheet_name}\n\n"
        f"**Lootsplit History Worksheet name:** {lootsplit_history_worksheet_name}\n\n"
        f"**Balance History Worksheet name:** {balance_history_worksheet_name}"
    )

    return f">>> {plain_message}"


async def post_or_update_bot_configuration_message(interaction: discord.Interaction) -> Tuple[bool, str]:
    if interaction.guild is None or interaction.channel is None:
        return False, "Cannot access channel in this context."

    content = _build_bot_configuration_message(interaction.guild.id)
    channel_id, message_id = guild_settings.get_bot_configuration_message(interaction.guild.id)

    if channel_id and message_id:
        try:
            target_channel = interaction.guild.get_channel(channel_id)
            if target_channel is None:
                target_channel = await interaction.guild.fetch_channel(channel_id)

            existing_message = await target_channel.fetch_message(message_id)
            await existing_message.edit(content=content)
            return True, "Bot configuration message updated."
        except discord.NotFound:
            pass
        except discord.Forbidden:
            return False, "Missing permission to edit the existing bot configuration message."
        except discord.HTTPException:
            return False, "Failed to update the existing bot configuration message."

    try:
        new_message = await interaction.channel.send(content)
    except discord.Forbidden:
        return False, "Missing permission to send messages in this channel."
    except discord.HTTPException:
        return False, "Failed to send bot configuration message."

    guild_settings.set_bot_configuration_message(interaction.guild.id, interaction.channel.id, new_message.id)
    return True, "Bot configuration message posted."


class BotSetupModal(discord.ui.Modal, title='Bot setup'):
    target_guild_name = discord.ui.TextInput(
        label='Enter your guild name',
        placeholder='Guild',
        required=True,
        max_length=30,
    )
    caller_role_name = discord.ui.TextInput(
        label='Caller Role Name(s)',
        placeholder='Default: Caller. Example: Caller, War Master',
        required=False,
        max_length=200,
    )
    member_role_name = discord.ui.TextInput(
        label='Member Role Name',
        placeholder='Default: Member. Role name MUST match.',
        required=False,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        success, message = _apply_server_setup(
            interaction.guild.id,
            str(self.target_guild_name).strip(),
            str(self.member_role_name).strip(),
            str(self.caller_role_name).strip() or "Caller",
        )
        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        posted, posted_message = await post_or_update_bot_configuration_message(interaction)
        if not posted:
            await interaction.followup.send(posted_message, ephemeral=True)
            return
        await interaction.followup.send(posted_message, ephemeral=True)


class GoogleSheetCredentialsModal(discord.ui.Modal, title='Link Google Sheet credentials'):
    credentials_json = discord.ui.TextInput(
        label='Credentials JSON',
        placeholder='Paste full Google service account JSON here',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )
    google_sheet_name = discord.ui.TextInput(
        label='Google Sheet Name',
        placeholder='Default: Guild name. Sheet name MUST match.',
        required=False,
        max_length=100,
    )
    google_worksheet_name = discord.ui.TextInput(
        label='Google Worksheet Name',
        placeholder='Default: Players. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )
    lootsplit_history_worksheet_name = discord.ui.TextInput(
        label='Lootsplit Worksheet Name',
        placeholder='Default: Lootsplit History. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )
    balance_history_worksheet_name = discord.ui.TextInput(
        label='Balance History Worksheet Name',
        placeholder='Default: Balance History. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        target_guild_name = guild_settings.get_target_guild(interaction.guild.id)
        if not target_guild_name:
            await interaction.response.send_message(
                "This server is not configured yet. Run **/bot-setup** first.",
                ephemeral=True,
            )
            return

        success, message = google_sheet_credentials_store.link_google_sheet_credentials(
            interaction.guild.id,
            target_guild_name,
            str(self.credentials_json),
            str(self.google_sheet_name),
            str(self.google_worksheet_name),
            str(self.lootsplit_history_worksheet_name),
            str(self.balance_history_worksheet_name),
        )
        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        posted, posted_message = await post_or_update_bot_configuration_message(interaction)
        if not posted:
            await interaction.followup.send(posted_message, ephemeral=True)
            return
        await interaction.followup.send(posted_message, ephemeral=True)
