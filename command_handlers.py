import asyncio
from datetime import datetime, timezone

import discord

import albion_client as client
import balance
import comp_builder
import globals
import google_sheet_credentials_store
import google_sheets
import guild_settings
import registration
from modals import BotSetupModal, GoogleSheetCredentialsModal, post_or_update_bot_configuration_message


def _parse_csv_names(raw_value: str) -> list[str]:
    return [value.strip() for value in raw_value.split(',') if value.strip()]


def _has_any_named_role(member: discord.Member, role_names: list[str]) -> bool:
    normalized = {name.strip().lower() for name in role_names if name.strip()}
    if not normalized:
        return False
    return any(role.name.lower() in normalized for role in member.roles)


def _has_economy_access(member: discord.Member, guild_id: int) -> bool:
    economy_roles = guild_settings.get_economy_manager_roles(guild_id)
    return _has_any_named_role(member, economy_roles)


async def handle_create_comp_from_message(bot, context, comp_message_id: int, source_channel_id: int = None):
    await context.message.delete()

    caller_roles = guild_settings.get_caller_roles(context.guild.id) if context.guild else []
    if not await globals.is_admin(context.author) and not comp_builder.has_caller_role(context.author, caller_roles):
        await context.send("You don't have permission to use this command.", delete_after=10)
        return

    if source_channel_id is None:
        await context.send("You must provide a **Channel ID** as a second parameter.")
        return

    source_channel = bot.get_channel(source_channel_id)
    if source_channel is None:
        await context.send("Could not find source channel. Make sure that **Channel ID** is correct.")
        return

    try:
        source_message = await source_channel.fetch_message(comp_message_id)
    except Exception:
        await context.send("Could not fetch comp message. Make sure that **Channel ID** was inserted correctly.")
        return

    parties = source_message.content.strip().split('\n\n')
    for party in parties:
        m = await context.send(party)
        thread_name = party.split('\n')[0] + " thread"
        await m.create_thread(name=thread_name, auto_archive_duration=60, slowmode_delay=10)


async def handle_get_battle_participants(context, battle_ids: str):
    await client.get_battle_participants(context, battle_ids)


async def handle_register(context, nickname: str):
    target_guild_name = guild_settings.get_target_guild(context.guild.id)
    worksheet = await google_sheets.get_server_worksheet_or_notice(context)
    if worksheet is None:
        return
    await registration.register_user(context, nickname, worksheet, target_guild_name)


async def handle_bot_setup_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_modal(BotSetupModal())


async def handle_bot_link_google_sheet_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_modal(GoogleSheetCredentialsModal())


async def handle_update_config_slash(bot, interaction: discord.Interaction):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    menu_text = (
        "## Which configuration you want to change?\n\n"
        "(1) Guild name\n"
        "(2) Caller role(s)\n"
        "(3) Economy Manager role(s)\n"
        "(4) Member role\n"
        "(5) Credentials file\n"
        "(6) Google Sheet name\n"
        "(7) Players Worksheet name\n"
        "(8) Lootsplit History Worksheet name\n"
        "(9) Balance History Worksheet name\n"
        "(10) Exit"
    )

    await interaction.response.send_message(menu_text)

    def message_check(message: discord.Message) -> bool:
        return (
            message.author.id == interaction.user.id
            and message.guild is not None
            and message.guild.id == interaction.guild.id
            and message.channel.id == interaction.channel.id
        )

    try:
        selection_message = await bot.wait_for("message", timeout=180.0, check=message_check)
    except asyncio.TimeoutError:
        await interaction.followup.send("Configuration update timed out.")
        return

    selection_raw = selection_message.content.strip()
    if not selection_raw.isdigit():
        await interaction.followup.send("Invalid selection. Send a number from 1 to 10.")
        return

    selection = int(selection_raw)
    if selection < 1 or selection > 10:
        await interaction.followup.send("Invalid selection. Send a number from 1 to 10.")
        return

    if selection == 10:
        await interaction.followup.send("Configuration update cancelled.")
        return

    option_labels = {
        1: "Guild name",
        2: "Caller role(s)",
        3: "Economy Manager role(s)",
        4: "Member role",
        5: "Credentials file",
        6: "Google Sheet name",
        7: "Players Worksheet name",
        8: "Lootsplit History Worksheet name",
        9: "Balance History Worksheet name",
    }

    label = option_labels[selection]
    await interaction.followup.send(f"Type new value for the **{label}**:")

    try:
        value_message = await bot.wait_for("message", timeout=180.0, check=message_check)
    except asyncio.TimeoutError:
        await interaction.followup.send("Configuration update timed out.")
        return

    new_value = value_message.content.strip()
    if not new_value:
        await interaction.followup.send("Value cannot be empty.")
        return

    if selection in (1, 2, 3, 4):
        current_guild_name = guild_settings.get_target_guild(interaction.guild.id)
        if not current_guild_name:
            await interaction.followup.send("This server is not configured yet. Run **/bot-setup** first.")
            return

        current_member_role = guild_settings.get_member_role(interaction.guild.id)
        current_caller_roles = ", ".join(guild_settings.get_caller_roles(interaction.guild.id))
        current_economy_manager_roles = ", ".join(guild_settings.get_economy_manager_roles(interaction.guild.id))

        updated_guild_name = current_guild_name
        updated_caller_roles = current_caller_roles
        updated_economy_manager_roles = current_economy_manager_roles
        updated_member_role = current_member_role

        if selection == 1:
            existing_server_id = guild_settings.get_server_id_by_target_guild(new_value)
            if existing_server_id and int(existing_server_id) != interaction.guild.id:
                await interaction.followup.send(
                    f"Guild name **{new_value}** is already used by another server. Exiting configuration setup."
                )
                return
            updated_guild_name = new_value
        elif selection == 2:
            updated_caller_roles = new_value
        elif selection == 3:
            updated_economy_manager_roles = new_value
        elif selection == 4:
            updated_member_role = new_value

        guild_settings.set_target_guild(
            interaction.guild.id,
            updated_guild_name,
            updated_member_role,
            updated_caller_roles,
            updated_economy_manager_roles,
        )
    else:
        link_field_by_option = {
            5: "credentials_file",
            6: "google_sheet_name",
            7: "google_worksheet_name",
            8: "lootsplit_history_worksheet_name",
            9: "balance_history_worksheet_name",
        }
        target_field = link_field_by_option[selection]
        updated, update_message = google_sheet_credentials_store.update_credentials_link_field(
            interaction.guild.id,
            target_field,
            new_value,
        )
        if not updated:
            await interaction.followup.send(update_message)
            return

    posted, posted_message = await post_or_update_bot_configuration_message(interaction)
    if not posted:
        await interaction.followup.send(posted_message)
        return

    await interaction.followup.send("Configuration updated.")


async def handle_lootsplit_slash(
    interaction: discord.Interaction,
    battle_ids: str,
    officer: str,
    content_name: str,
    caller: str,
    participants: str,
    lootsplit_amount: str,
):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    has_access = await globals.is_admin(interaction.user) or _has_economy_access(interaction.user, interaction.guild.id)
    if not has_access:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    players_worksheet = await google_sheets.get_server_worksheet_or_notice(interaction.channel)
    if players_worksheet is None:
        await interaction.followup.send("Unable to open Players worksheet.")
        return

    lootsplit_worksheet = await google_sheets.get_server_lootsplit_history_worksheet_or_notice(interaction.channel)
    if lootsplit_worksheet is None:
        await interaction.followup.send("Unable to open Lootsplit History worksheet.")
        return

    try:
        lootsplit_amount_int = int(lootsplit_amount)
    except ValueError:
        await interaction.followup.send("`lootsplit_amount` must be an integer.")
        return

    if lootsplit_amount_int < 0:
        await interaction.followup.send("`lootsplit_amount` must be >= 0.")
        return

    battle_id_list = _parse_csv_names(battle_ids)
    if not battle_id_list:
        await interaction.followup.send("Please provide at least one battle ID.")
        return

    participant_list = _parse_csv_names(participants)
    if not participant_list:
        await interaction.followup.send("Please provide at least one participant.")
        return

    google_sheets.ensure_lootsplit_history_headers(lootsplit_worksheet)

    date_utc = datetime.now(timezone.utc).strftime("%m/%d/%y %H:%M UTC")
    battle_ids_normalized = ",".join(battle_id_list)

    credited_mentions = []
    missing_participants = []
    failed_participants = []

    try:
        credited, missing_participants = balance.add_balances_for_lootsplit_batch(
            players_worksheet,
            participant_list,
            lootsplit_amount_int,
        )
    except Exception:
        failed_participants = list(dict.fromkeys(participant_list))
        credited = []

    history_rows: list[list[str]] = []
    for participant_name, discord_id in credited:
        history_rows.append([
            battle_ids_normalized,
            date_utc,
            officer,
            content_name,
            caller,
            participant_name,
            str(lootsplit_amount_int),
        ])
        credited_mentions.append(f"<@{discord_id}>")

    try:
        google_sheets.add_lootsplit_history_rows(lootsplit_worksheet, history_rows)
    except Exception:
        failed_from_history = [participant_name for participant_name, _ in credited]
        for participant_name in failed_from_history:
            if participant_name not in failed_participants:
                failed_participants.append(participant_name)

    try:
        bh_worksheet = google_sheets.get_worksheet(
            interaction.guild.id,
            worksheet_type=google_sheets.WORKSHEET_TYPE_BALANCE_HISTORY,
        )
        google_sheets.ensure_balance_history_headers(bh_worksheet)
        google_sheets.add_balance_history_rows(bh_worksheet, [
            [date_utc, "Lootsplit", officer, participant_name, str(lootsplit_amount_int)]
            for participant_name, _ in credited
        ])
    except Exception:
        pass

    lines = [f"Lootsplit for **{content_name}**:"]
    if credited_mentions:
        for mention in credited_mentions:
            lines.append(f"{mention}: {lootsplit_amount_int};")
    else:
        lines.append("No participants were processed successfully.")

    if missing_participants:
        lines.append("")
        lines.append(f"Missing players: **{', '.join(missing_participants)}**")

    if failed_participants:
        lines.append("")
        lines.append(f"Failed to process: **{', '.join(failed_participants)}**")

    await interaction.followup.send("\n".join(lines))


async def handle_bot_remove(bot, context):
    if not await globals.is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return

    if context.guild is None:
        await context.reply("This command can only be used inside a server.")
        return

    configured_guild_name = guild_settings.get_target_guild(context.guild.id)
    if not configured_guild_name:
        await context.reply("This server is not set up.")
        return

    await context.reply(
        f"Warning: this will delete setup for this server (guild **{configured_guild_name}**). Reply with **YES** to proceed or **NO** to cancel."
    )

    def remove_confirmation_check(message: discord.Message) -> bool:
        return (
            message.author.id == context.author.id
            and message.channel.id == context.channel.id
            and message.content.strip().upper() in {"YES", "NO"}
        )

    try:
        confirmation_message = await bot.wait_for('message', timeout=60, check=remove_confirmation_check)
    except asyncio.TimeoutError:
        await context.reply("Removal timed out. Run !bot-remove again.")
        return

    if confirmation_message.content.strip().upper() != "YES":
        await context.reply("Removal cancelled.")
        return

    removed_guild_name = guild_settings.remove_target_guild(context.guild.id)
    if not removed_guild_name:
        await context.reply("This server is not set up.")
        return

    google_sheet_credentials_store.remove_google_sheet_credentials(context.guild.id)

    await context.reply(
        f"Setup removed. Discord server ID **{context.guild.id}** and guild **{removed_guild_name}** were deleted."
    )


async def handle_get_balance(context, nickname: str = None):
    worksheet = await google_sheets.get_server_worksheet_or_notice(context)
    if worksheet is None:
        return
    await balance.get_balance(context, worksheet, nickname)


async def handle_bal_add_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    add_silver: str,
    reason: str = "Manual",
):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    has_access = await globals.is_admin(interaction.user) or _has_economy_access(interaction.user, interaction.guild.id)
    if not has_access:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    try:
        amount_int = int(add_silver)
    except ValueError:
        await interaction.response.send_message("`add_silver` must be an integer.", ephemeral=True)
        return

    if amount_int < 0:
        await interaction.response.send_message("`add_silver` must be >= 0.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    players_worksheet = await google_sheets.get_server_worksheet_or_notice(interaction.channel)
    if players_worksheet is None:
        await interaction.followup.send("Unable to open Players worksheet.")
        return

    try:
        all_rows = players_worksheet.get_all_values()
    except Exception:
        await interaction.followup.send("Failed to read Players worksheet. Try again.")
        return

    officer_result = balance.find_player_by_discord_id(all_rows, interaction.user.id)
    officer_name = officer_result[1] if officer_result else interaction.user.display_name

    try:
        target_update = balance.update_member_balance_by_discord_id(
            players_worksheet,
            all_rows,
            member.id,
            amount_int,
            clamp_min_zero=False,
        )
    except Exception:
        await interaction.followup.send("Failed to update balance. Try again.")
        return

    if target_update is None:
        await interaction.followup.send(f"{member.mention} is not registered in the Players worksheet.")
        return

    target_nickname, updated_silver = target_update

    date_utc = datetime.now(timezone.utc).strftime("%m/%d/%y %H:%M UTC")
    history_note = ""
    try:
        bh_worksheet = google_sheets.get_worksheet(
            interaction.guild.id,
            worksheet_type=google_sheets.WORKSHEET_TYPE_BALANCE_HISTORY,
        )
        google_sheets.ensure_balance_history_headers(bh_worksheet)
        google_sheets.add_balance_history_row(bh_worksheet, date_utc, reason, officer_name, target_nickname, amount_int)
    except Exception:
        history_note = "\n*(Balance History entry could not be written.)*"

    await interaction.followup.send(f"{member.mention} balance: **{updated_silver}** :coin:{history_note}")


async def handle_bal_remove_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    remove_silver: str,
    reason: str = "Payout",
):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    has_access = await globals.is_admin(interaction.user) or _has_economy_access(interaction.user, interaction.guild.id)
    if not has_access:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    try:
        amount_int = int(remove_silver)
    except ValueError:
        await interaction.response.send_message("`remove_silver` must be an integer.", ephemeral=True)
        return

    if amount_int < 0:
        await interaction.response.send_message("`remove_silver` must be >= 0.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    players_worksheet = await google_sheets.get_server_worksheet_or_notice(interaction.channel)
    if players_worksheet is None:
        await interaction.followup.send("Unable to open Players worksheet.")
        return

    try:
        all_rows = players_worksheet.get_all_values()
    except Exception:
        await interaction.followup.send("Failed to read Players worksheet. Try again.")
        return

    officer_result = balance.find_player_by_discord_id(all_rows, interaction.user.id)
    officer_name = officer_result[1] if officer_result else interaction.user.display_name

    try:
        target_update = balance.update_member_balance_by_discord_id(
            players_worksheet,
            all_rows,
            member.id,
            -amount_int,
            clamp_min_zero=True,
        )
    except Exception:
        await interaction.followup.send("Failed to update balance. Try again.")
        return

    if target_update is None:
        await interaction.followup.send(f"{member.mention} is not registered in the Players worksheet.")
        return

    target_nickname, updated_silver = target_update

    date_utc = datetime.now(timezone.utc).strftime("%m/%d/%y %H:%M UTC")
    history_note = ""
    try:
        bh_worksheet = google_sheets.get_worksheet(
            interaction.guild.id,
            worksheet_type=google_sheets.WORKSHEET_TYPE_BALANCE_HISTORY,
        )
        google_sheets.ensure_balance_history_headers(bh_worksheet)
        google_sheets.add_balance_history_row(bh_worksheet, date_utc, reason, officer_name, target_nickname, -amount_int)
    except Exception:
        history_note = "\n*(Balance History entry could not be written.)*"

    await interaction.followup.send(f"{member.mention} balance: **{updated_silver}** :coin:{history_note}")


async def handle_clear(context):
    if not await globals.is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return

    await context.channel.purge()
