from datetime import datetime, timezone

import discord

import albion_client as client
import balance
from bot_remove import handle_bot_remove_slash
import comp_builder
import globals
import google_sheets
import guild_settings
import registration
from bot_setup import BotSetupStepView, _build_bot_setup_step_embed
from link_google_sheet import GoogleSheetLinkStepView, _build_google_sheet_link_step_embed
from update_config_panel import UpdateConfigView, _build_update_config_embed


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


class _InteractionMessageAdapter:
    def __init__(self, interaction: discord.Interaction):
        self._interaction = interaction
        self.guild = interaction.guild
        self.author = interaction.user

    async def send(self, content: str = None, **kwargs):
        if not self._interaction.response.is_done():
            await self._interaction.response.send_message(content, **kwargs)
        else:
            await self._interaction.followup.send(content, **kwargs)


def _build_balance_update_embed(
    actor: discord.Member,
    target: discord.Member,
    action_text: str,
    amount_text: str,
    reason: str,
    old_balance: int,
    new_balance: int,
    history_failed: bool = False,
) -> discord.Embed:
    embed = discord.Embed(
        color=discord.Color.blurple(),
        description=f"### {actor.mention} {action_text} {amount_text} balance {'to' if action_text == 'added' else 'from'} {target.mention}",
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Old balance", value=f"{old_balance:,} :coin:", inline=False)
    embed.add_field(name="New balance", value=f"{new_balance:,} :coin:", inline=False)

    if history_failed:
        embed.set_footer(text="Balance History entry could not be written.")

    return embed


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


async def handle_register_slash(interaction: discord.Interaction, character_name: str):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    interaction_context = _InteractionMessageAdapter(interaction)
    target_guild_name = guild_settings.get_target_guild(interaction.guild.id)
    worksheet = await google_sheets.get_server_worksheet_or_notice(interaction_context)
    if worksheet is None:
        return

    await registration.register_user(interaction_context, character_name, worksheet, target_guild_name)


async def handle_bot_setup_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    setup_view = BotSetupStepView(interaction.guild, interaction.user.id)
    await interaction.response.send_message(
        embed=_build_bot_setup_step_embed(setup_view),
        view=setup_view,
    )
    setup_view.host_message = await interaction.original_response()


async def handle_bot_link_google_sheet_slash(interaction: discord.Interaction):
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

    setup_view = GoogleSheetLinkStepView(interaction.guild, interaction.user.id)
    await interaction.response.send_message(
        embed=_build_google_sheet_link_step_embed(setup_view),
        view=setup_view,
    )
    setup_view.host_message = await interaction.original_response()


async def handle_update_config_slash(interaction: discord.Interaction):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    update_view = UpdateConfigView(interaction.guild, interaction.user.id)
    await interaction.response.send_message(
        embed=_build_update_config_embed(update_view),
        view=update_view,
    )
    update_view.host_message = await interaction.original_response()


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


async def handle_get_balance(context, member: discord.Member = None):
    worksheet = await google_sheets.get_server_worksheet_or_notice(context)
    if worksheet is None:
        return
    await balance.get_balance(context, worksheet, member)


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

    target_nickname, previous_silver, updated_silver = target_update

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
        history_note = True

    embed = _build_balance_update_embed(
        interaction.user,
        member,
        "added",
        f"{amount_int:,}",
        reason,
        previous_silver,
        updated_silver,
        history_failed=history_note,
    )
    await interaction.followup.send(embed=embed)


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

    target_nickname, previous_silver, updated_silver = target_update

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
        history_note = True

    embed = _build_balance_update_embed(
        interaction.user,
        member,
        "removed",
        f"-{amount_int:,}",
        reason,
        previous_silver,
        updated_silver,
        history_failed=history_note,
    )
    await interaction.followup.send(embed=embed)


async def handle_clear(context):
    if not await globals.is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return

    await context.channel.purge()


async def handle_clear_slash(interaction: discord.Interaction) -> None:
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("This command can only be used in a text channel.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        await interaction.channel.purge(limit=100)
    except discord.Forbidden:
        await interaction.followup.send(
            "Missing permission to delete messages in this channel.",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            "Failed to clear messages (Discord API error).",
            ephemeral=True,
        )
        return

    await interaction.followup.send("Cleared the last 100 messages.", ephemeral=True)
