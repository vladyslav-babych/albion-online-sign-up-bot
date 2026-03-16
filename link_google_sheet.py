import discord
import guild_settings
import google_sheet_credentials_store
import json
import re
from typing import Optional

from bot_configuration_panel import post_or_update_bot_configuration_message


def _sanitize_guild_name_for_credentials(guild_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", guild_name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "guild"


def _build_credentials_file_name_preview(guild_name: str) -> str:
    return f"{_sanitize_guild_name_for_credentials(guild_name)}_credentials.json"


def _build_google_sheet_link_step_embed(view: "GoogleSheetLinkStepView") -> discord.Embed:
    state = view.state
    embed = discord.Embed(title=f"Link Google Sheet - Step {view.step}/6")

    if view.step == 1:
        embed.description = (
            "## :identification_card: Insert Google service account credentials JSON via modal\n\n"
            "## :warning: Warning:\n"
            "### Service account credentials are stored as local JSON files and bot owner/operator can access them."
        )
        embed.add_field(name="Credentials file to be created", value=state["credentials_file_name_preview"], inline=False)
    elif view.step == 2:
        embed.description = (
            "## :pencil: Set Google Sheet name \n\n"
            "## :exclamation: Important:\n"
            "### The Google Sheet name MUST match the name specified in the modal and the linked Google Sheet."
        )
        embed.add_field(name="Selected Google Sheet name", value=state["google_sheet_name"], inline=False)
    elif view.step == 3:
        embed.description = (
            "## :pencil: Set Players worksheet name \n\n"
            "## :exclamation: Important:\n"
            "### The Players worksheet name MUST match the name specified in the modal and the linked Google Sheet."
        )
        embed.add_field(name="Selected Players worksheet", value=state["google_worksheet_name"], inline=False)
    elif view.step == 4:
        embed.description = (
            "## :pencil: Set Lootsplit History worksheet name \n\n"
            "## :exclamation: Important:\n"
            "### The Lootsplit History worksheet name MUST match the name specified in the modal and the linked Google Sheet."
        )
        embed.add_field(name="Selected Lootsplit History worksheet", value=state["lootsplit_history_worksheet_name"], inline=False)
    elif view.step == 5:
        embed.description = (
            "## :pencil: Set Balance History worksheet name \n\n"
            "## :exclamation: Important:\n"
            "### The Balance History worksheet name MUST match the name specified in the modal and the linked Google Sheet."
        )
        embed.add_field(name="Selected Balance History worksheet", value=state["balance_history_worksheet_name"], inline=False)
    else:
        embed.description = "## :mag: Review summary and finish linking"
        embed.add_field(name="Credentials file", value=state["credentials_file_name_preview"], inline=False)
        embed.add_field(name="Google Sheet name", value=state["google_sheet_name"], inline=False)
        embed.add_field(name="Players worksheet", value=state["google_worksheet_name"], inline=False)
        embed.add_field(name="Lootsplit History worksheet", value=state["lootsplit_history_worksheet_name"], inline=False)
        embed.add_field(name="Balance History worksheet", value=state["balance_history_worksheet_name"], inline=False)

    return embed


class GoogleCredentialsJsonModal(discord.ui.Modal, title='Set Credentials JSON'):
    credentials_json = discord.ui.TextInput(
        label='Credentials JSON',
        placeholder='Paste full Google service account JSON here',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    def __init__(self, parent_view: "GoogleSheetLinkStepView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_credentials = str(self.credentials_json)

        try:
            parsed_credentials = json.loads(raw_credentials)
        except json.JSONDecodeError:
            await interaction.response.send_message("Credentials text is not valid JSON.", ephemeral=True)
            return

        if not isinstance(parsed_credentials, dict):
            await interaction.response.send_message("Credentials JSON must be an object.", ephemeral=True)
            return

        required_keys = {"client_email", "private_key", "project_id"}
        missing_keys = [key for key in required_keys if key not in parsed_credentials]
        if missing_keys:
            await interaction.response.send_message(
                f"Credentials JSON is missing required key(s): {', '.join(missing_keys)}.",
                ephemeral=True,
            )
            return

        self.parent_view.state["credentials_json"] = raw_credentials
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_google_sheet_link_step_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Credentials JSON captured.", ephemeral=True)


class GoogleSheetNameModal(discord.ui.Modal, title='Set Google Sheet Name'):
    google_sheet_name = discord.ui.TextInput(
        label='Google Sheet Name',
        placeholder='Default: Guild name. Sheet name MUST match.',
        required=False,
        max_length=100,
    )

    def __init__(self, parent_view: "GoogleSheetLinkStepView"):
        super().__init__()
        self.parent_view = parent_view
        self.google_sheet_name.default = parent_view.state["google_sheet_name"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.state["google_sheet_name"] = str(self.google_sheet_name).strip() or self.parent_view.state["google_sheet_name"]
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_google_sheet_link_step_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Google Sheet name updated.", ephemeral=True)


class GooglePlayersWorksheetModal(discord.ui.Modal, title='Set Players Worksheet Name'):
    google_worksheet_name = discord.ui.TextInput(
        label='Players Worksheet Name',
        placeholder='Default: Players. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )

    def __init__(self, parent_view: "GoogleSheetLinkStepView"):
        super().__init__()
        self.parent_view = parent_view
        self.google_worksheet_name.default = parent_view.state["google_worksheet_name"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.state["google_worksheet_name"] = str(self.google_worksheet_name).strip() or "Players"
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_google_sheet_link_step_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Players worksheet name updated.", ephemeral=True)


class GoogleLootsplitWorksheetModal(discord.ui.Modal, title='Set Lootsplit History Worksheet Name'):
    lootsplit_history_worksheet_name = discord.ui.TextInput(
        label='Lootsplit History Worksheet Name',
        placeholder='Default: Lootsplit History. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )

    def __init__(self, parent_view: "GoogleSheetLinkStepView"):
        super().__init__()
        self.parent_view = parent_view
        self.lootsplit_history_worksheet_name.default = parent_view.state["lootsplit_history_worksheet_name"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.state["lootsplit_history_worksheet_name"] = (
            str(self.lootsplit_history_worksheet_name).strip() or "Lootsplit History"
        )
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_google_sheet_link_step_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Lootsplit History worksheet name updated.", ephemeral=True)


class GoogleBalanceWorksheetModal(discord.ui.Modal, title='Set Balance History Worksheet Name'):
    balance_history_worksheet_name = discord.ui.TextInput(
        label='Balance History Worksheet Name',
        placeholder='Default: Balance History. Worksheet name MUST match.',
        required=False,
        max_length=100,
    )

    def __init__(self, parent_view: "GoogleSheetLinkStepView"):
        super().__init__()
        self.parent_view = parent_view
        self.balance_history_worksheet_name.default = parent_view.state["balance_history_worksheet_name"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.state["balance_history_worksheet_name"] = (
            str(self.balance_history_worksheet_name).strip() or "Balance History"
        )
        if self.parent_view.host_message is not None:
            await self.parent_view.host_message.edit(
                embed=_build_google_sheet_link_step_embed(self.parent_view),
                view=self.parent_view,
            )
        await interaction.response.send_message("Balance History worksheet name updated.", ephemeral=True)


class GoogleSheetLinkStepView(discord.ui.View):
    def __init__(self, guild: discord.Guild, user_id: int, step: int = 1, state: Optional[dict] = None):
        super().__init__(timeout=900)
        self.guild = guild
        self.user_id = user_id
        target_guild_name = guild_settings.get_target_guild(guild.id) or "guild"
        self.step = step
        self.state = state or {
            "credentials_json": "",
            "credentials_file_name_preview": _build_credentials_file_name_preview(target_guild_name),
            "google_sheet_name": target_guild_name,
            "google_worksheet_name": "Players",
            "lootsplit_history_worksheet_name": "Lootsplit History",
            "balance_history_worksheet_name": "Balance History",
        }
        self.host_message: Optional[discord.Message] = None
        self._build_items()

    async def ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the admin who started this setup can use these controls.", ephemeral=True)
            return False
        return True

    def _build_items(self) -> None:
        self.clear_items()
        self.add_item(GoogleSheetLinkBackButton())
        if self.step == 1:
            self.add_item(GoogleSetCredentialsButton())
            self.add_item(GoogleSheetLinkContinueButton())
            self.add_item(GoogleSheetLinkCancelButton())
        elif self.step == 2:
            self.add_item(GoogleSetSheetNameButton())
            self.add_item(GoogleSheetLinkContinueButton())
        elif self.step == 3:
            self.add_item(GoogleSetPlayersWorksheetButton())
            self.add_item(GoogleSheetLinkContinueButton())
        elif self.step == 4:
            self.add_item(GoogleSetLootsplitWorksheetButton())
            self.add_item(GoogleSheetLinkContinueButton())
        elif self.step == 5:
            self.add_item(GoogleSetBalanceWorksheetButton())
            self.add_item(GoogleSheetLinkContinueButton())
        else:
            self.add_item(GoogleSheetLinkFinishButton())
            self.add_item(GoogleSheetLinkCancelButton())

    def next_step(self) -> None:
        self.step = min(6, self.step + 1)
        self._build_items()

    def previous_step(self) -> None:
        self.step = max(1, self.step - 1)
        self._build_items()


class GoogleSheetLinkBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        view.previous_step()
        await interaction.response.edit_message(embed=_build_google_sheet_link_step_embed(view), view=view)


class GoogleSetCredentialsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Credentials JSON", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.send_modal(GoogleCredentialsJsonModal(view))


class GoogleSetSheetNameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Google Sheet Name", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.send_modal(GoogleSheetNameModal(view))


class GoogleSetPlayersWorksheetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Players Worksheet", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.send_modal(GooglePlayersWorksheetModal(view))


class GoogleSetLootsplitWorksheetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Lootsplit Worksheet", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.send_modal(GoogleLootsplitWorksheetModal(view))


class GoogleSetBalanceWorksheetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Balance Worksheet", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.send_modal(GoogleBalanceWorksheetModal(view))


class GoogleSheetLinkContinueButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Save and Continue", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return

        if view.step == 1 and not view.state["credentials_json"].strip():
            await interaction.response.send_message("Set credentials JSON first.", ephemeral=True)
            return

        view.next_step()
        await interaction.response.edit_message(embed=_build_google_sheet_link_step_embed(view), view=view)


class GoogleSheetLinkFinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Finish", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return

        target_guild_name = guild_settings.get_target_guild(view.guild.id)
        if not target_guild_name:
            await interaction.response.send_message("This server is not configured yet. Run **/bot-setup** first.", ephemeral=True)
            return

        success, message = google_sheet_credentials_store.link_google_sheet_credentials(
            view.guild.id,
            target_guild_name,
            view.state["credentials_json"],
            view.state["google_sheet_name"],
            view.state["google_worksheet_name"],
            view.state["lootsplit_history_worksheet_name"],
            view.state["balance_history_worksheet_name"],
        )
        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if interaction.message is not None:
            await interaction.message.edit(
                embed=discord.Embed(title="Link Google Sheet", description="Link setup completed."),
                view=None,
            )

        posted, posted_message = await post_or_update_bot_configuration_message(interaction)
        if not posted:
            await interaction.followup.send(posted_message, ephemeral=True)
            return
        await interaction.followup.send(posted_message, ephemeral=True)


class GoogleSheetLinkCancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GoogleSheetLinkStepView):
            return
        if not await view.ensure_owner(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(title="Link Google Sheet", description="Link setup cancelled."),
            view=None,
        )
