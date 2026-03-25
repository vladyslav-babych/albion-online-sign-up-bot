import discord
import guild_settings
import google_sheet_credentials_store
from pathlib import Path
from typing import Optional

from bot_configuration_panel import _format_named_role_mentions, post_or_update_bot_configuration_message
from bot_setup import _format_role_mentions_by_ids, _resolve_role_names


_UPDATE_CONFIG_LABELS = {
    "guild_name": "Guild name",
    "caller_roles": "Caller role(s)",
    "economy_roles": "Economy Manager role(s)",
    "member_role": "Member role",
    "leave_action": "Leave guild action",
    "credentials_file": "Credentials file",
    "google_sheet_name": "Google Sheet name",
    "players_worksheet": "Players Worksheet name",
    "lootsplit_worksheet": "Lootsplit History Worksheet name",
    "balance_worksheet": "Balance History Worksheet name",
}


def _format_leave_action(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "kick":
        return "Kick from server"
    if normalized == "remove_roles":
        return "Remove all roles"
    if normalized == "none":
        return "Do nothing"
    return "Not configured yet"


def _resolve_role_ids_by_names(guild: discord.Guild, role_names: list[str]) -> list[int]:
    normalized = {role_name.strip().lower() for role_name in role_names if role_name.strip()}
    if not normalized:
        return []
    return [role.id for role in guild.roles if role.name.strip().lower() in normalized]


def _get_update_config_current_text(guild_id: int, field_key: str) -> str:
    if field_key == "guild_name":
        return guild_settings.get_target_guild(guild_id) or ""
    if field_key == "leave_action":
        return guild_settings.get_leave_action(guild_id) or ""
    if field_key == "credentials_file":
        info = google_sheet_credentials_store.get_credentials_info(guild_id)
        credentials_path = info.get("credentials_file") if info else None
        return Path(str(credentials_path)).name if credentials_path else ""
    if field_key == "google_sheet_name":
        return (google_sheet_credentials_store.get_credentials_info(guild_id) or {}).get("google_sheet_name") or ""
    if field_key == "players_worksheet":
        return (google_sheet_credentials_store.get_credentials_info(guild_id) or {}).get("google_worksheet_name") or ""
    if field_key == "lootsplit_worksheet":
        return (google_sheet_credentials_store.get_credentials_info(guild_id) or {}).get("lootsplit_history_worksheet_name") or ""
    if field_key == "balance_worksheet":
        return (google_sheet_credentials_store.get_credentials_info(guild_id) or {}).get("balance_history_worksheet_name") or ""
    return ""


def _get_update_config_current_role_ids(guild: discord.Guild, field_key: str) -> list[int]:
    if field_key == "caller_roles":
        return _resolve_role_ids_by_names(guild, guild_settings.get_caller_roles(guild.id))
    if field_key == "economy_roles":
        return _resolve_role_ids_by_names(guild, guild_settings.get_economy_manager_roles(guild.id))
    if field_key == "member_role":
        return _resolve_role_ids_by_names(guild, [guild_settings.get_member_role(guild.id)])
    return []


def _get_update_config_current_preview(guild: discord.Guild, field_key: str) -> str:
    if field_key == "leave_action":
        return _format_leave_action(guild_settings.get_leave_action(guild.id))
    if field_key == "caller_roles":
        return _format_named_role_mentions(guild, guild_settings.get_caller_roles(guild.id))
    if field_key == "economy_roles":
        return _format_named_role_mentions(guild, guild_settings.get_economy_manager_roles(guild.id))
    if field_key == "member_role":
        return _format_named_role_mentions(guild, [guild_settings.get_member_role(guild.id)])

    current_value = _get_update_config_current_text(guild.id, field_key)
    return current_value or "Not configured yet"


def _build_update_config_embed(view: "UpdateConfigView") -> discord.Embed:
    embed = discord.Embed(title="Update Configuration")

    if view.selected_field_key is None:
        embed.description = "Select which configuration you want to change."
    else:
        field_label = _UPDATE_CONFIG_LABELS[view.selected_field_key]
        embed.description = f"Update **{field_label}** using the controls below."
        embed.add_field(name="Selected option", value=field_label, inline=False)
        embed.add_field(
            name="Current value",
            value=_get_update_config_current_preview(view.guild, view.selected_field_key),
            inline=False,
        )
        if view.selected_field_key in {"caller_roles", "economy_roles", "member_role"}:
            embed.add_field(
                name="Preview",
                value=_format_role_mentions_by_ids(view.guild, view.pending_role_ids),
                inline=False,
            )
        elif view.selected_field_key == "leave_action":
            embed.add_field(name="Preview", value=_format_leave_action(view.pending_text_value), inline=False)
        else:
            embed.add_field(name="Preview", value=view.pending_text_value or "Not configured yet", inline=False)

    if view.status_message:
        embed.add_field(name="Status", value=view.status_message, inline=False)

    return embed


class UpdateConfigValueModal(discord.ui.Modal):
    def __init__(self, parent_view: "UpdateConfigView", title: str, label: str, placeholder: str, default_value: str):
        super().__init__(title=title)
        self.parent_view = parent_view
        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=200,
            default=default_value,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.pending_text_value = str(self.value_input).strip()
        self.parent_view.status_message = None
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_update_config_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Value updated in preview.", ephemeral=True)


class UpdateConfigFieldSelect(discord.ui.Select):
    def __init__(self, selected_field_key: Optional[str], custom_id: str):
        options = [
            discord.SelectOption(label=label, value=key)
            for key, label in _UPDATE_CONFIG_LABELS.items()
        ]
        super().__init__(
            placeholder="Which configuration you want to change?",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        view.selected_field_key = self.values[0]
        view.load_pending_from_current()
        view._build_items()
        await interaction.response.edit_message(embed=_build_update_config_embed(view), view=view)


class UpdateConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, field_key: str, custom_id: str):
        is_member_role = field_key == "member_role"
        placeholder = _UPDATE_CONFIG_LABELS[field_key]
        super().__init__(
            placeholder=f"Select {placeholder}",
            min_values=1,
            max_values=1 if is_member_role else 25,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        view.pending_role_ids = [role.id for role in self.values]
        view.status_message = None
        await interaction.response.edit_message(embed=_build_update_config_embed(view), view=view)


class UpdateConfigLeaveActionSelect(discord.ui.Select):
    def __init__(self, custom_id: str):
        options = [
            discord.SelectOption(label="Kick from server", value="kick"),
            discord.SelectOption(label="Remove all roles", value="remove_roles"),
            discord.SelectOption(label="Do nothing", value="none"),
        ]
        super().__init__(
            placeholder="Choose action when player leaves the guild",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        view.pending_text_value = self.values[0]
        view.status_message = None
        await interaction.response.edit_message(embed=_build_update_config_embed(view), view=view)


class UpdateConfigOpenModalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Value", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        if view.selected_field_key is None:
            await interaction.response.send_message("Select a configuration field first.", ephemeral=True)
            return

        field_key = view.selected_field_key
        titles = {
            "guild_name": "Set Guild Name",
            "credentials_file": "Set Credentials File",
            "google_sheet_name": "Set Google Sheet Name",
            "players_worksheet": "Set Players Worksheet Name",
            "lootsplit_worksheet": "Set Lootsplit History Worksheet Name",
            "balance_worksheet": "Set Balance History Worksheet Name",
        }
        placeholders = {
            "guild_name": "Guild name",
            "credentials_file": "Existing file in google_sheet_credentials/",
            "google_sheet_name": "Google Sheet name",
            "players_worksheet": "Players",
            "lootsplit_worksheet": "Lootsplit History",
            "balance_worksheet": "Balance History",
        }
        await interaction.response.send_modal(
            UpdateConfigValueModal(
                view,
                titles[field_key],
                _UPDATE_CONFIG_LABELS[field_key],
                placeholders[field_key],
                view.pending_text_value,
            )
        )


class UpdateConfigSaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Save Change", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        if view.selected_field_key is None:
            await interaction.response.send_message("Select a configuration field first.", ephemeral=True)
            return

        field_key = view.selected_field_key

        if field_key in {"guild_name", "caller_roles", "economy_roles", "member_role", "leave_action"}:
            current_guild_name = guild_settings.get_target_guild(interaction.guild.id)
            if not current_guild_name:
                await interaction.response.send_message("This server is not configured yet. Run **/bot-setup** first.", ephemeral=True)
                return

            updated_guild_name = current_guild_name
            updated_caller_roles = ", ".join(guild_settings.get_caller_roles(interaction.guild.id))
            updated_economy_manager_roles = ", ".join(guild_settings.get_economy_manager_roles(interaction.guild.id))
            updated_member_role = guild_settings.get_member_role(interaction.guild.id)
            updated_leave_action = guild_settings.get_leave_action(interaction.guild.id)

            if field_key == "guild_name":
                new_value = view.pending_text_value.strip()
                if not new_value:
                    await interaction.response.send_message("Value cannot be empty.", ephemeral=True)
                    return
                existing_server_id = guild_settings.get_server_id_by_target_guild(new_value)
                if existing_server_id and int(existing_server_id) != interaction.guild.id:
                    await interaction.response.send_message(
                        f"Guild name **{new_value}** is already used by another server.",
                        ephemeral=True,
                    )
                    return
                updated_guild_name = new_value
            elif field_key == "caller_roles":
                if not view.pending_role_ids:
                    await interaction.response.send_message("Select at least one Caller role.", ephemeral=True)
                    return
                updated_caller_roles = ", ".join(_resolve_role_names(interaction.guild, view.pending_role_ids))
            elif field_key == "economy_roles":
                if not view.pending_role_ids:
                    await interaction.response.send_message("Select at least one Economy Manager role.", ephemeral=True)
                    return
                updated_economy_manager_roles = ", ".join(_resolve_role_names(interaction.guild, view.pending_role_ids))
            elif field_key == "member_role":
                if not view.pending_role_ids:
                    await interaction.response.send_message("Select Member role.", ephemeral=True)
                    return
                member_role_names = _resolve_role_names(interaction.guild, view.pending_role_ids)
                updated_member_role = member_role_names[0] if member_role_names else "Member"
            elif field_key == "leave_action":
                new_value = (view.pending_text_value or "").strip().lower()
                if new_value not in {"kick", "remove_roles", "none"}:
                    await interaction.response.send_message("Select a valid leave action.", ephemeral=True)
                    return
                updated_leave_action = new_value

            guild_settings.set_target_guild(
                interaction.guild.id,
                updated_guild_name,
                updated_member_role,
                updated_caller_roles,
                updated_economy_manager_roles,
                updated_leave_action,
            )
        else:
            link_field_map = {
                "credentials_file": "credentials_file",
                "google_sheet_name": "google_sheet_name",
                "players_worksheet": "google_worksheet_name",
                "lootsplit_worksheet": "lootsplit_history_worksheet_name",
                "balance_worksheet": "balance_history_worksheet_name",
            }
            updated, update_message = google_sheet_credentials_store.update_credentials_link_field(
                interaction.guild.id,
                link_field_map[field_key],
                view.pending_text_value,
            )
            if not updated:
                await interaction.response.send_message(update_message, ephemeral=True)
                return

        posted, posted_message = await post_or_update_bot_configuration_message(interaction)
        view.load_pending_from_current()
        view.status_message = "Configuration updated." if posted else f"Configuration updated, but bot configuration panel failed to refresh: {posted_message}"
        view._build_items()
        await interaction.response.edit_message(embed=_build_update_config_embed(view), view=view)


class UpdateConfigCancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, UpdateConfigView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(title="Update Configuration", description="Configuration update cancelled."),
            view=None,
        )


class UpdateConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, user_id: int):
        super().__init__(timeout=900)
        self.guild = guild
        self.user_id = user_id
        self.host_message: Optional[discord.Message] = None
        self.selected_field_key: Optional[str] = None
        self.pending_text_value = ""
        self.pending_role_ids: list[int] = []
        self.status_message: Optional[str] = None
        self._render_nonce = 0
        self._build_items()

    async def ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the admin who opened configuration update can use these controls.", ephemeral=True)
            return False
        return True

    def load_pending_from_current(self) -> None:
        if self.selected_field_key is None:
            self.pending_text_value = ""
            self.pending_role_ids = []
            return
        if self.selected_field_key in {"caller_roles", "economy_roles", "member_role"}:
            self.pending_role_ids = _get_update_config_current_role_ids(self.guild, self.selected_field_key)
            self.pending_text_value = ""
        else:
            self.pending_text_value = _get_update_config_current_text(self.guild.id, self.selected_field_key)
            self.pending_role_ids = []

    def _build_items(self) -> None:
        self._render_nonce += 1
        self.clear_items()
        self.add_item(UpdateConfigFieldSelect(self.selected_field_key, custom_id=f"update-config-field-{self._render_nonce}"))
        if self.selected_field_key in {"caller_roles", "economy_roles", "member_role"}:
            self.add_item(UpdateConfigRoleSelect(self.selected_field_key, custom_id=f"update-config-role-{self._render_nonce}"))
            self.add_item(UpdateConfigSaveButton())
        elif self.selected_field_key == "leave_action":
            self.add_item(UpdateConfigLeaveActionSelect(custom_id=f"update-config-leave-action-{self._render_nonce}"))
            self.add_item(UpdateConfigSaveButton())
        elif self.selected_field_key is not None:
            self.add_item(UpdateConfigOpenModalButton())
            self.add_item(UpdateConfigSaveButton())
        self.add_item(UpdateConfigCancelButton())
