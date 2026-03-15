import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

import discord

import globals


_TICKETS_FILE = Path("configs/tickets_config.json")


def _load_ticket_config() -> dict:
	if not _TICKETS_FILE.exists():
		return {}

	try:
		with _TICKETS_FILE.open("r", encoding="utf-8") as file:
			data = json.load(file)
	except (json.JSONDecodeError, OSError):
		return {}

	return data if isinstance(data, dict) else {}


def _save_ticket_config(config: dict) -> None:
	with _TICKETS_FILE.open("w", encoding="utf-8") as file:
		json.dump(config, file, ensure_ascii=True, indent=2)


def _ensure_guild_entry(config: dict, guild_id: int) -> dict:
	guild_key = str(guild_id)
	entry = config.get(guild_key)
	if not isinstance(entry, dict):
		entry = {"next_ticket_number": 1, "panels": {}}
		config[guild_key] = entry

	entry.setdefault("next_ticket_number", 1)
	entry.setdefault("panels", {})
	return entry


def _list_panels(guild_id: int) -> list[dict]:
	config = _load_ticket_config()
	entry = _ensure_guild_entry(config, guild_id)
	panels = entry.get("panels", {})
	if not isinstance(panels, dict):
		return []
	return list(panels.values())


def _get_panel_by_id(guild_id: int, panel_id: str) -> Optional[dict]:
	config = _load_ticket_config()
	entry = _ensure_guild_entry(config, guild_id)
	panels = entry.get("panels", {})
	if not isinstance(panels, dict):
		return None
	panel = panels.get(panel_id)
	return panel if isinstance(panel, dict) else None


def _get_panel_by_message_id(guild_id: int, message_id: int) -> Optional[dict]:
	for panel in _list_panels(guild_id):
		if int(panel.get("panel_message_id", 0) or 0) == message_id:
			return panel
	return None


def _save_panel(guild_id: int, panel: dict) -> None:
	config = _load_ticket_config()
	entry = _ensure_guild_entry(config, guild_id)
	panels = entry.setdefault("panels", {})
	panels[str(panel["id"])] = panel
	_save_ticket_config(config)


def _delete_panel(guild_id: int, panel_id: str) -> None:
	config = _load_ticket_config()
	entry = _ensure_guild_entry(config, guild_id)
	panels = entry.get("panels", {})
	if isinstance(panels, dict):
		panels.pop(str(panel_id), None)
	_save_ticket_config(config)


def _consume_ticket_number(guild_id: int) -> int:
	config = _load_ticket_config()
	entry = _ensure_guild_entry(config, guild_id)
	current_number = int(entry.get("next_ticket_number", 1) or 1)
	entry["next_ticket_number"] = current_number + 1
	_save_ticket_config(config)
	return current_number


def _format_role_mentions(guild: discord.Guild, role_ids: list[int]) -> str:
	mentions = []
	for role_id in role_ids:
		role = guild.get_role(int(role_id))
		if role is not None:
			mentions.append(role.mention)
	return ", ".join(mentions) if mentions else "Not selected"


def _format_role_names(guild: discord.Guild, role_ids: list[int]) -> str:
	names = []
	for role_id in role_ids:
		role = guild.get_role(int(role_id))
		if role is not None:
			names.append(role.name)
	return ", ".join(names) if names else "Not selected"


def _format_category_name(guild: discord.Guild, category_id: Optional[int]) -> str:
	if not category_id:
		return "Not selected"
	category = guild.get_channel(int(category_id))
	return category.name if category is not None else "Not selected"


def _format_channel_mention(guild: discord.Guild, channel_id: Optional[int]) -> str:
	if not channel_id:
		return "Not selected"
	channel = guild.get_channel(int(channel_id))
	return channel.mention if channel is not None else "Not selected"


def _has_management_access(member: discord.Member, management_role_ids: list[int]) -> bool:
	if any(role.permissions.administrator for role in member.roles):
		return True
	member_role_ids = {role.id for role in member.roles}
	return any(int(role_id) in member_role_ids for role_id in management_role_ids)


def _build_ticket_topic(panel_id: str, opener_id: int, ticket_number: int) -> str:
	return f"panel_id={panel_id};opener_id={opener_id};ticket_number={ticket_number}"


def _parse_ticket_topic(topic: Optional[str]) -> dict[str, str]:
	if not topic:
		return {}

	result = {}
	for part in topic.split(";"):
		if "=" not in part:
			continue
		key, value = part.split("=", 1)
		result[key.strip()] = value.strip()
	return result


def _find_existing_open_ticket_channel(guild: discord.Guild, panel_id: str, opener_id: int) -> Optional[discord.TextChannel]:
	for channel in guild.text_channels:
		if channel.name.startswith("closed-"):
			continue

		metadata = _parse_ticket_topic(channel.topic)
		if metadata.get("panel_id") != str(panel_id):
			continue
		if metadata.get("opener_id") != str(opener_id):
			continue
		return channel

	return None


def _get_default_panel_message() -> str:
	return "Click the button below to open a ticket."


def _get_default_ticket_message() -> str:
	return "Use this channel for the guild application. Management team can close it when review is complete."


def _build_panel_embed(panel_name: str, panel_message: Optional[str] = None) -> discord.Embed:
	embed = discord.Embed(title=panel_name, description=panel_message or _get_default_panel_message())
	return embed


def _build_setup_embed(view: "TicketPanelSetupView") -> discord.Embed:
	embed = discord.Embed(title=f"Ticket Panel Setup - Step {view.step}/6")
	state = view.state
	guild = view.guild

	if view.step == 1:
		embed.description = "Set the panel name."
		embed.add_field(name="Panel name", value=state["panel_name"], inline=False)
	elif view.step == 2:
		embed.description = "Select the management team role(s)."
		embed.add_field(
			name="Selected management team roles",
			value=_format_role_mentions(guild, state["management_role_ids"]),
			inline=False,
		)
	elif view.step == 3:
		embed.description = "Select the ticket category."
		embed.add_field(
			name="Selected category",
			value=_format_category_name(guild, state["ticket_category_id"]),
			inline=False,
		)
	elif view.step == 4:
		embed.description = "Select the panel destination channel."
		embed.add_field(
			name="Selected panel destination",
			value=_format_channel_mention(guild, state["panel_destination_channel_id"]),
			inline=False,
		)
	elif view.step == 5:
		embed.description = "Set the panel message and the opening ticket message."
		embed.add_field(name="Panel message", value=state["panel_message"], inline=False)
		embed.add_field(name="Ticket message", value=state["ticket_message"], inline=False)
	else:
		embed.description = "Review the summary and finish panel creation."
		embed.add_field(name="Panel name", value=state["panel_name"], inline=False)
		embed.add_field(
			name="Management team role(s)",
			value=_format_role_mentions(guild, state["management_role_ids"]),
			inline=False,
		)
		embed.add_field(
			name="Ticket category",
			value=_format_category_name(guild, state["ticket_category_id"]),
			inline=False,
		)
		embed.add_field(
			name="Panel destination",
			value=_format_channel_mention(guild, state["panel_destination_channel_id"]),
			inline=False,
		)
		embed.add_field(name="Panel message", value=state["panel_message"], inline=False)
		embed.add_field(name="Ticket message", value=state["ticket_message"], inline=False)
		embed.add_field(name="Panel preview", value=f"**{state['panel_name']}**\n{state['panel_message']}", inline=False)

	return embed


def _build_home_embed(guild: discord.Guild) -> discord.Embed:
	embed = discord.Embed(title="Tickets Setup", description="Choose how you want to configure the ticket system.")
	embed.add_field(name="Guild", value=guild.name, inline=False)
	return embed


def _build_manage_embed(guild: discord.Guild, panels: list[dict], selected_panel_id: Optional[str]) -> discord.Embed:
	embed = discord.Embed(title="Manage Ticket Panels")
	if not panels:
		embed.description = "No ticket panels are configured yet."
		return embed

	selected_panel = None
	for panel in panels:
		if panel.get("id") == selected_panel_id:
			selected_panel = panel
			break
	if selected_panel is None:
		selected_panel = panels[0]

	embed.description = "Select a panel to resend or delete it."
	embed.add_field(name="Panel name", value=selected_panel.get("panel_name", "Unknown"), inline=False)
	embed.add_field(
		name="Management team role(s)",
		value=_format_role_mentions(guild, selected_panel.get("management_role_ids", [])),
		inline=False,
	)
	embed.add_field(
		name="Ticket category",
		value=_format_category_name(guild, selected_panel.get("ticket_category_id")),
		inline=False,
	)
	embed.add_field(
		name="Panel destination",
		value=_format_channel_mention(guild, selected_panel.get("panel_destination_channel_id") or selected_panel.get("panel_channel_id")),
		inline=False,
	)
	embed.add_field(name="Panel message", value=selected_panel.get("panel_message") or _get_default_panel_message(), inline=False)
	embed.add_field(name="Ticket message", value=selected_panel.get("ticket_message") or _get_default_ticket_message(), inline=False)
	embed.add_field(
		name="Panel channel",
		value=_format_channel_mention(guild, selected_panel.get("panel_channel_id")),
		inline=False,
	)
	return embed


class PanelNameModal(discord.ui.Modal, title="Set Panel Name"):
	panel_name = discord.ui.TextInput(label="Panel name", required=True, max_length=100, default="Panel Name")

	def __init__(self, parent_view: "TicketPanelSetupView"):
		super().__init__()
		self.parent_view = parent_view
		self.panel_name.default = parent_view.state["panel_name"]

	async def on_submit(self, interaction: discord.Interaction) -> None:
		self.parent_view.state["panel_name"] = str(self.panel_name).strip() or "Panel Name"
		if self.parent_view.host_message is not None:
			await self.parent_view.host_message.edit(embed=_build_setup_embed(self.parent_view), view=self.parent_view)
		await interaction.response.send_message("Panel name updated.", ephemeral=True)


class PanelMessagesModal(discord.ui.Modal, title="Set Ticket Messages"):
	panel_message = discord.ui.TextInput(label="Panel message", style=discord.TextStyle.paragraph, required=True, max_length=1000)
	ticket_message = discord.ui.TextInput(label="Ticket opening message", style=discord.TextStyle.paragraph, required=True, max_length=1000)

	def __init__(self, parent_view: "TicketPanelSetupView"):
		super().__init__()
		self.parent_view = parent_view
		self.panel_message.default = parent_view.state["panel_message"]
		self.ticket_message.default = parent_view.state["ticket_message"]

	async def on_submit(self, interaction: discord.Interaction) -> None:
		self.parent_view.state["panel_message"] = str(self.panel_message).strip() or _get_default_panel_message()
		self.parent_view.state["ticket_message"] = str(self.ticket_message).strip() or _get_default_ticket_message()
		if self.parent_view.host_message is not None:
			await self.parent_view.host_message.edit(embed=_build_setup_embed(self.parent_view), view=self.parent_view)
		await interaction.response.send_message("Ticket messages updated.", ephemeral=True)


class ManagementRoleSelect(discord.ui.RoleSelect):
	def __init__(self):
		super().__init__(placeholder="Select all roles for management team", min_values=1, max_values=25)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		view.state["management_role_ids"] = [role.id for role in self.values]
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class TicketCategorySelect(discord.ui.ChannelSelect):
	def __init__(self):
		super().__init__(placeholder="Select the ticket category", channel_types=[discord.ChannelType.category], min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		selected = self.values[0]
		view.state["ticket_category_id"] = selected.id
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class PanelDestinationChannelSelect(discord.ui.ChannelSelect):
	def __init__(self):
		super().__init__(placeholder="Select panel destination channel", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		selected = self.values[0]
		view.state["panel_destination_channel_id"] = selected.id
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class TicketPanelSetupView(discord.ui.View):
	def __init__(self, bot, guild: discord.Guild, user_id: int, setup_channel: discord.abc.Messageable, state: Optional[dict] = None, step: int = 1):
		super().__init__(timeout=900)
		self.bot = bot
		self.guild = guild
		self.user_id = user_id
		self.setup_channel = setup_channel
		self.step = step
		self.state = state or {
			"panel_name": "Panel Name",
			"management_role_ids": [],
			"ticket_category_id": None,
			"panel_destination_channel_id": None,
			"panel_message": _get_default_panel_message(),
			"ticket_message": _get_default_ticket_message(),
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
		self.add_item(SetupBackButton())
		if self.step == 1:
			self.add_item(SetPanelNameButton())
			self.add_item(SetupContinueButton())
			self.add_item(CancelSetupButton())
		elif self.step == 2:
			self.add_item(ManagementRoleSelect())
			self.add_item(SetupContinueButton())
		elif self.step == 3:
			self.add_item(TicketCategorySelect())
			self.add_item(SetupContinueButton())
		elif self.step == 4:
			self.add_item(PanelDestinationChannelSelect())
			self.add_item(SetupContinueButton())
		elif self.step == 5:
			self.add_item(SetPanelMessagesButton())
			self.add_item(SetupContinueButton())
		else:
			self.add_item(FinishPanelButton())

	def next_step(self) -> None:
		self.step += 1
		self._build_items()

	def previous_step(self) -> None:
		self.step = max(1, self.step - 1)
		self._build_items()


class SetupBackButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		view.previous_step()
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class SetPanelNameButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set panel name", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.send_modal(PanelNameModal(view))


class SetPanelMessagesButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set messages", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.send_modal(PanelMessagesModal(view))


class CancelSetupButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Cancel Setup", style=discord.ButtonStyle.danger)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.edit_message(
			embed=_build_home_embed(view.guild),
			view=TicketsSetupHomeView(view.bot, view.user_id, view.guild),
		)


class SetupContinueButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Save and Continue", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		if view.step == 2 and not view.state["management_role_ids"]:
			await interaction.response.send_message("Select at least one management team role.", ephemeral=True)
			return
		if view.step == 3 and not view.state["ticket_category_id"]:
			await interaction.response.send_message("Select a ticket category.", ephemeral=True)
			return
		if view.step == 4 and not view.state["panel_destination_channel_id"]:
			await interaction.response.send_message("Select a panel destination channel.", ephemeral=True)
			return

		view.next_step()
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class FinishPanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Finish", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketPanelSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		panel_destination_channel = view.guild.get_channel(int(view.state["panel_destination_channel_id"] or 0))
		if not isinstance(panel_destination_channel, discord.TextChannel):
			await interaction.response.send_message("Configured panel destination channel was not found.", ephemeral=True)
			return

		panel_id = uuid4().hex[:10]
		panel_message = await panel_destination_channel.send(
			embed=_build_panel_embed(view.state["panel_name"], view.state["panel_message"]),
			view=TicketOpenView(view.bot),
		)

		panel = {
			"id": panel_id,
			"panel_name": view.state["panel_name"],
			"management_role_ids": view.state["management_role_ids"],
			"ticket_category_id": view.state["ticket_category_id"],
			"panel_destination_channel_id": view.state["panel_destination_channel_id"],
			"panel_message": view.state["panel_message"],
			"ticket_message": view.state["ticket_message"],
			"panel_channel_id": panel_message.channel.id,
			"panel_message_id": panel_message.id,
		}
		_save_panel(view.guild.id, panel)

		await interaction.response.edit_message(
			embed=discord.Embed(title="Ticket panel created", description=f"Panel **{panel['panel_name']}** was posted in {panel_message.channel.mention}."),
			view=TicketsSetupHomeView(view.bot, view.user_id, view.guild),
		)


class ManagePanelSelect(discord.ui.Select):
	def __init__(self, panels: list[dict], selected_panel_id: Optional[str]):
		options = [
			discord.SelectOption(label=panel.get("panel_name", "Panel"), value=str(panel.get("id")), default=str(panel.get("id")) == str(selected_panel_id))
			for panel in panels[:25]
		]
		super().__init__(placeholder="Select panel", min_values=1, max_values=1, options=options)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if not await view.ensure_owner(interaction):
			return
		view.selected_panel_id = self.values[0]
		view._build_items()
		await interaction.response.edit_message(embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id), view=view)


class ManagePanelsView(discord.ui.View):
	def __init__(self, bot, guild: discord.Guild, user_id: int, panels: list[dict], selected_panel_id: Optional[str] = None):
		super().__init__(timeout=900)
		self.bot = bot
		self.guild = guild
		self.user_id = user_id
		self.panels = panels
		self.selected_panel_id = selected_panel_id or (str(panels[0].get("id")) if panels else None)
		self._build_items()

	async def ensure_owner(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.user_id:
			await interaction.response.send_message("Only the admin who opened panel management can use these controls.", ephemeral=True)
			return False
		return True

	def _get_selected_panel(self) -> Optional[dict]:
		for panel in self.panels:
			if str(panel.get("id")) == str(self.selected_panel_id):
				return panel
		return self.panels[0] if self.panels else None

	def _build_items(self) -> None:
		self.clear_items()
		if self.panels:
			self.add_item(ManagePanelSelect(self.panels, self.selected_panel_id))
			self.add_item(ResendPanelButton())
			self.add_item(DeletePanelButton())
		self.add_item(ManageBackButton())


class ResendPanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Send Panel Again", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if not await view.ensure_owner(interaction):
			return

		panel = view._get_selected_panel()
		if panel is None:
			await interaction.response.send_message("No panel selected.", ephemeral=True)
			return

		panel_channel = (
			view.guild.get_channel(int(panel.get("panel_destination_channel_id", 0) or 0))
			or view.guild.get_channel(int(panel.get("panel_channel_id", 0) or 0))
			or interaction.channel
		)
		panel_message = await panel_channel.send(
			embed=_build_panel_embed(panel.get("panel_name", "Panel Name"), panel.get("panel_message") or _get_default_panel_message()),
			view=TicketOpenView(view.bot),
		)
		panel["panel_message_id"] = panel_message.id
		panel["panel_channel_id"] = panel_message.channel.id
		_save_panel(view.guild.id, panel)
		view.panels = _list_panels(view.guild.id)
		await interaction.response.edit_message(embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id), view=view)


class DeletePanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Delete Panel", style=discord.ButtonStyle.danger)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if not await view.ensure_owner(interaction):
			return

		panel = view._get_selected_panel()
		if panel is None:
			await interaction.response.send_message("No panel selected.", ephemeral=True)
			return

		channel_id = int(panel.get("panel_channel_id", 0) or 0)
		message_id = int(panel.get("panel_message_id", 0) or 0)
		target_channel = view.guild.get_channel(channel_id)
		if target_channel is not None and message_id:
			try:
				target_message = await target_channel.fetch_message(message_id)
				await target_message.delete()
			except Exception:
				pass

		_delete_panel(view.guild.id, str(panel.get("id")))
		view.panels = _list_panels(view.guild.id)
		view.selected_panel_id = str(view.panels[0].get("id")) if view.panels else None
		await interaction.response.edit_message(embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id), view=view)


class ManageBackButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.edit_message(embed=_build_home_embed(view.guild), view=TicketsSetupHomeView(view.bot, view.user_id, view.guild))


class CreatePanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Create Panel", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketsSetupHomeView):
			return
		if not await view.ensure_owner(interaction):
			return

		setup_view = TicketPanelSetupView(view.bot, view.guild, view.user_id, interaction.channel)
		setup_view.host_message = interaction.message
		await interaction.response.edit_message(embed=_build_setup_embed(setup_view), view=setup_view)


class OpenManagePanelsButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Manage Panels", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, TicketsSetupHomeView):
			return
		if not await view.ensure_owner(interaction):
			return

		panels = _list_panels(view.guild.id)
		manage_view = ManagePanelsView(view.bot, view.guild, view.user_id, panels)
		await interaction.response.edit_message(embed=_build_manage_embed(view.guild, panels, manage_view.selected_panel_id), view=manage_view)


class TicketsSetupHomeView(discord.ui.View):
	def __init__(self, bot, user_id: int, guild: discord.Guild):
		super().__init__(timeout=900)
		self.bot = bot
		self.user_id = user_id
		self.guild = guild
		self.add_item(CreatePanelButton())
		self.add_item(OpenManagePanelsButton())

	async def ensure_owner(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.user_id:
			await interaction.response.send_message("Only the admin who opened ticket setup can use these controls.", ephemeral=True)
			return False
		return True


class TicketOpenView(discord.ui.View):
	def __init__(self, bot):
		super().__init__(timeout=None)
		self.bot = bot

	@discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, custom_id="tickets:open")
	async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
		if interaction.guild is None:
			await interaction.response.send_message("This button can only be used inside a server.", ephemeral=True)
			return

		panel = _get_panel_by_message_id(interaction.guild.id, interaction.message.id)
		if panel is None:
			await interaction.response.send_message("Ticket panel configuration was not found.", ephemeral=True)
			return

		category = interaction.guild.get_channel(int(panel.get("ticket_category_id", 0) or 0))
		if not isinstance(category, discord.CategoryChannel):
			await interaction.response.send_message("Configured ticket category was not found.", ephemeral=True)
			return

		existing_ticket_channel = _find_existing_open_ticket_channel(
			interaction.guild,
			str(panel.get("id")),
			interaction.user.id,
		)
		if existing_ticket_channel is not None:
			await interaction.response.send_message(
				f"You already have an open ticket: {existing_ticket_channel.mention}",
				ephemeral=True,
			)
			return

		ticket_number = _consume_ticket_number(interaction.guild.id)
		ticket_name = f"ticket-{ticket_number:04d}"
		overwrites = {
			interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
			interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
			interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True),
		}

		for role_id in panel.get("management_role_ids", []):
			role = interaction.guild.get_role(int(role_id))
			if role is not None:
				overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

		channel = await interaction.guild.create_text_channel(
			name=ticket_name,
			category=category,
			overwrites=overwrites,
			topic=_build_ticket_topic(str(panel.get("id")), interaction.user.id, ticket_number),
		)

		management_names = _format_role_names(interaction.guild, panel.get("management_role_ids", []))
		embed = discord.Embed(
			title=f"Ticket {ticket_number:04d}",
			description=panel.get("ticket_message") or _get_default_ticket_message(),
		)
		embed.add_field(name="Applicant", value=interaction.user.mention, inline=False)
		embed.add_field(name="Management team", value=management_names, inline=False)
		await channel.send(content=interaction.user.mention, embed=embed, view=TicketCloseView(self.bot))

		await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


class TicketCloseView(discord.ui.View):
	def __init__(self, bot):
		super().__init__(timeout=None)
		self.bot = bot

	@discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="tickets:close")
	async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
		if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
			await interaction.response.send_message("This button can only be used inside a ticket channel.", ephemeral=True)
			return

		if not isinstance(interaction.user, discord.Member):
			await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
			return

		metadata = _parse_ticket_topic(interaction.channel.topic)
		panel_id = metadata.get("panel_id")
		ticket_number_raw = metadata.get("ticket_number", "0")
		opener_id_raw = metadata.get("opener_id", "0")
		panel = _get_panel_by_id(interaction.guild.id, panel_id) if panel_id else None
		if panel is None:
			await interaction.response.send_message("Ticket configuration was not found.", ephemeral=True)
			return

		if not _has_management_access(interaction.user, panel.get("management_role_ids", [])):
			await interaction.response.send_message("Only the management team can close this ticket.", ephemeral=True)
			return

		if interaction.channel.name.startswith("closed-"):
			await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
			return

		await interaction.response.defer(ephemeral=True)

		opener_member = interaction.guild.get_member(int(opener_id_raw or 0)) if opener_id_raw.isdigit() else None

		new_name = f"closed-{int(ticket_number_raw or 0):04d}" if str(ticket_number_raw).isdigit() else f"closed-{interaction.channel.id}"
		await interaction.channel.edit(name=new_name)
		if opener_member is not None:
			await interaction.channel.set_permissions(opener_member, send_messages=False, add_reactions=False)

		await interaction.channel.send(f"Ticket closed by {interaction.user.mention}.")
		await interaction.followup.send("Ticket closed.", ephemeral=True)


async def handle_tickets_setup(bot, interaction: discord.Interaction):
	if interaction.guild is None:
		await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
		return

	if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
		await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
		return

	home_view = TicketsSetupHomeView(bot, interaction.user.id, interaction.guild)
	await interaction.response.send_message(embed=_build_home_embed(interaction.guild), view=home_view)


def register_persistent_views(bot) -> None:
	bot.add_view(TicketOpenView(bot))
	bot.add_view(TicketCloseView(bot))
