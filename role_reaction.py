import json
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

import discord
import emoji

import globals


_ROLE_REACTION_FILE = Path("configs/role_reaction_config.json")
_MAX_REACTIONS_PER_PANEL = 6


async def _send_ephemeral_notice(interaction: discord.Interaction, text: str) -> None:
	if interaction.response.is_done():
		await interaction.followup.send(text, ephemeral=True)
	else:
		await interaction.response.send_message(text, ephemeral=True)

def _strip_variation_selectors(value: str) -> str:
	return (value or "").replace("\ufe0f", "")


def _extract_single_unicode_emoji(value: str) -> Optional[str]:
	text = (value or "").strip()
	if not text:
		return None

	found = emoji.emoji_list(text)
	if len(found) != 1:
		return None

	emoji_char = found[0].get("emoji")
	if not isinstance(emoji_char, str) or not emoji_char:
		return None

	remainder = text.replace(emoji_char, "", 1).strip()
	if remainder:
		return None

	return emoji_char


def _normalize_emoji_input(raw_value: str) -> Optional[str]:
	value = (raw_value or "").strip()
	if not value:
		return None

	if any(not c.isascii() for c in value):
		return _extract_single_unicode_emoji(value)

	if value.startswith(":") and value.endswith(":") and len(value) > 2:
		converted = emoji.emojize(value, language="alias")
		if converted != value:
			return _extract_single_unicode_emoji(converted)

		converted = emoji.emojize(value)
		if converted != value:
			return _extract_single_unicode_emoji(converted)

	return None


def _emoji_key(emoji_raw: str) -> str:
	return _strip_variation_selectors((emoji_raw or "").strip())


def _emoji_matches(left: str, right: str) -> bool:
	return _emoji_key(left) == _emoji_key(right)


async def _add_panel_reaction(message: discord.Message, raw_emoji: str) -> None:
	normalized = _normalize_emoji_input(raw_emoji)
	if not normalized:
		logging.warning("Skipping invalid reaction emoji %s for message %s", raw_emoji, message.id)
		return

	try:
		await message.add_reaction(normalized)
	except discord.HTTPException as err:
		logging.warning("Could not add reaction %s: %s", normalized, err)

def _load_config() -> dict:
	if not _ROLE_REACTION_FILE.exists():
		return {}

	try:
		with _ROLE_REACTION_FILE.open("r", encoding="utf-8") as f:
			data = json.load(f)
	except (json.JSONDecodeError, OSError):
		return {}

	return data if isinstance(data, dict) else {}


def _save_config(config: dict) -> None:
	_ROLE_REACTION_FILE.parent.mkdir(parents=True, exist_ok=True)
	with _ROLE_REACTION_FILE.open("w", encoding="utf-8") as f:
		json.dump(config, f, ensure_ascii=True, indent=2)


def _guild_entry(config: dict, guild_id: int) -> dict:
	key = str(guild_id)
	if not isinstance(config.get(key), dict):
		config[key] = {"panels": {}}
	config[key].setdefault("panels", {})
	return config[key]


def _list_panels(guild_id: int) -> list[dict]:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	panels = entry.get("panels", {})
	return list(panels.values()) if isinstance(panels, dict) else []


def _get_panel_by_message_id(guild_id: int, message_id: int) -> Optional[dict]:
	for panel in _list_panels(guild_id):
		if int(panel.get("panel_message_id", 0) or 0) == int(message_id):
			return panel
	return None


def _save_panel(guild_id: int, panel: dict) -> None:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	entry["panels"][str(panel["id"])] = panel
	_save_config(config)


def _delete_panel(guild_id: int, panel_id: str) -> None:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	panels = entry.get("panels", {})
	if isinstance(panels, dict):
		panels.pop(str(panel_id), None)
	_save_config(config)

def _format_role_mention(guild: discord.Guild, role_id: Optional[int]) -> str:
	if not role_id:
		return "Not selected"
	role = guild.get_role(int(role_id))
	return role.mention if role is not None else "Not selected"


def _format_channel_mention(guild: discord.Guild, channel_id: Optional[int]) -> str:
	if not channel_id:
		return "Not selected"
	ch = guild.get_channel(int(channel_id))
	return ch.mention if ch is not None else "Not selected"


def _format_role_reaction_list(guild: discord.Guild, reactions: list[dict]) -> str:
	if not reactions:
		return "None"
	lines: list[str] = []
	for item in reactions:
		role = guild.get_role(int(item.get("role_id", 0) or 0))
		role_mention = role.mention if role is not None else f"<unknown role {item.get('role_id')}>"
		lines.append(f"{item.get('emoji', '')} ‒ {role_mention}")
	return "\n".join(lines)


def _build_panel_embed(panel_name: str, panel_message: str, guild: discord.Guild, reactions: list[dict]) -> discord.Embed:
	description = panel_message
	if reactions:
		description += "\n\n" + _format_role_reaction_list(guild, reactions)
	return discord.Embed(title=panel_name, description=description)


def _build_home_embed(guild: discord.Guild) -> discord.Embed:
	embed = discord.Embed(
		title="Role Reaction Setup",
		description="## :gear: Choose an option below to manage role reaction panels.",
	)
	return embed


def _build_setup_embed(view: "RoleReactionSetupView") -> discord.Embed:
	state = view.state
	guild = view.guild
	step = view.step

	embed = discord.Embed(title=f"Role Reaction Panel Setup — Step {step}/5")

	if step == 1:
		embed.description = "## :pencil: Set panel name"
		embed.add_field(name="Panel name", value=state["panel_name"] or "Not set", inline=False)
	elif step == 2:
		embed.description = "## :speech_balloon: Set panel message"
		embed.add_field(name="Panel message", value=state["panel_message"], inline=False)
	elif step == 3:
		embed.description = (
			"## :label: Set emoji → associated role\n"
			f"Up to {_MAX_REACTIONS_PER_PANEL} role reactions."
		)
		embed.add_field(
			name=f"Role reactions ({len(state['reactions'])}/{_MAX_REACTIONS_PER_PANEL})",
			value=_format_role_reaction_list(guild, state["reactions"]),
			inline=False,
		)
	elif step == 4:
		embed.description = "## :satellite: Select destination channel"
		embed.add_field(
			name="Destination channel",
			value=_format_channel_mention(guild, state["destination_channel_id"]),
			inline=False,
		)
	else:
		embed.description = "## :clipboard: Preview and final confirmation"
		embed.add_field(name="Panel name", value=state["panel_name"] or "Not set", inline=False)
		embed.add_field(name="Panel message", value=state["panel_message"], inline=False)
		embed.add_field(
			name=f"Role reactions ({len(state['reactions'])}/{_MAX_REACTIONS_PER_PANEL})",
			value=_format_role_reaction_list(guild, state["reactions"]),
			inline=False,
		)
		embed.add_field(
			name="Destination channel",
			value=_format_channel_mention(guild, state["destination_channel_id"]),
			inline=False,
		)
		embed.add_field(
			name="Panel preview",
			value=f"**{state['panel_name']}**\n{state['panel_message']}",
			inline=False,
		)

	return embed


def _build_picker_embed(picker: "RoleReactionPickerView") -> discord.Embed:
	emoji_display = picker.selected_emoji_raw or "*(not selected)*"
	role_display = f"<@&{picker.selected_role_id}>" if picker.selected_role_id else "*(not selected)*"
	embed = discord.Embed(title="Add Role Reaction")
	embed.add_field(name="Emoji", value=emoji_display, inline=True)
	embed.add_field(name="Role", value=role_display, inline=True)
	return embed


def _build_manage_embed(guild: discord.Guild, panels: list[dict], selected_panel_id: Optional[str]) -> discord.Embed:
	embed = discord.Embed(title="Manage Role Reaction Panels")
	if not panels:
		embed.description = "No role reaction panels configured yet."
		return embed

	selected = next((p for p in panels if str(p.get("id")) == str(selected_panel_id)), panels[0])
	embed.description = "Select a panel to resend it or delete it."
	embed.add_field(name="Panel name", value=selected.get("panel_name", "Unknown"), inline=False)
	embed.add_field(name="Panel message", value=selected.get("panel_message", ""), inline=False)
	embed.add_field(
		name="Role reactions",
		value=_format_role_reaction_list(guild, selected.get("reactions", [])),
		inline=False,
	)
	embed.add_field(
		name="Destination channel",
		value=_format_channel_mention(guild, selected.get("destination_channel_id")),
		inline=False,
	)
	return embed

class PanelNameModal(discord.ui.Modal, title="Set Panel Name"):
	panel_name = discord.ui.TextInput(
		label="Panel name",
		required=True,
		max_length=100,
		default="Panel name",
	)

	def __init__(self, parent_view: "RoleReactionSetupView"):
		super().__init__()
		self.parent_view = parent_view
		self.panel_name.default = parent_view.state["panel_name"]

	async def on_submit(self, interaction: discord.Interaction) -> None:
		self.parent_view.state["panel_name"] = str(self.panel_name).strip() or "Panel name"
		await interaction.response.edit_message(
			embed=_build_setup_embed(self.parent_view),
			view=self.parent_view,
		)


class PanelMessageModal(discord.ui.Modal, title="Set Panel Message"):
	panel_message = discord.ui.TextInput(
		label="Panel message",
		style=discord.TextStyle.paragraph,
		required=True,
		max_length=1000,
	)

	def __init__(self, parent_view: "RoleReactionSetupView"):
		super().__init__()
		self.parent_view = parent_view
		self.panel_message.default = parent_view.state["panel_message"]

	async def on_submit(self, interaction: discord.Interaction) -> None:
		self.parent_view.state["panel_message"] = (
			str(self.panel_message).strip() or "React to the following emojis to get role."
		)
		await interaction.response.edit_message(
			embed=_build_setup_embed(self.parent_view),
			view=self.parent_view,
		)


class _EmojiInputModal(discord.ui.Modal, title="Select Emoji"):
	emoji_input = discord.ui.TextInput(
		label="Paste or type an emoji",
		placeholder="e.g. 🎮 or :gear:",
		required=True,
		max_length=50,
	)

	def __init__(self, picker: "RoleReactionPickerView"):
		super().__init__()
		self._picker = picker
		if picker.selected_emoji_raw:
			self.emoji_input.default = picker.selected_emoji_raw

	async def on_submit(self, interaction: discord.Interaction) -> None:
		self._picker.selected_emoji_raw = str(self.emoji_input).strip()
		self._picker._build_items()
		await interaction.response.edit_message(embed=_build_picker_embed(self._picker), view=self._picker)


class RoleReactionPickerView(discord.ui.View):
	def __init__(self, parent_view: "RoleReactionSetupView", nonce: int):
		super().__init__(timeout=300)
		self.parent_view = parent_view
		self._nonce = nonce
		self.selected_emoji_raw: Optional[str] = None
		self.selected_role_id: Optional[int] = None
		self._build_items()

	def _build_items(self) -> None:
		self.clear_items()
		self.add_item(_PickerBackButton(self))
		self.add_item(_EmojiSelectButton(self))
		self.add_item(_RolePickerSelect(custom_id=f"rr-role-{self._nonce}"))
		self.add_item(_SaveReactionButton(self))


class _PickerBackButton(discord.ui.Button):
	def __init__(self, picker: RoleReactionPickerView):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary, custom_id=f"rr-pick-back-{picker._nonce}")
		self._picker = picker

	async def callback(self, interaction: discord.Interaction) -> None:
		if interaction.user.id != self._picker.parent_view.user_id:
			return
		parent = self._picker.parent_view
		parent._build_items()
		await interaction.response.edit_message(embed=_build_setup_embed(parent), view=parent)


class _EmojiSelectButton(discord.ui.Button):
	def __init__(self, picker: RoleReactionPickerView):
		label = f"Selected emoji: {picker.selected_emoji_raw}" if picker.selected_emoji_raw else "Select emoji"
		super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"rr-emoji-btn-{picker._nonce}")
		self._picker = picker

	async def callback(self, interaction: discord.Interaction) -> None:
		if interaction.user.id != self._picker.parent_view.user_id:
			return
		await interaction.response.send_modal(_EmojiInputModal(self._picker))


class _RolePickerSelect(discord.ui.RoleSelect):
	def __init__(self, custom_id: str):
		super().__init__(
			placeholder="Select role",
			min_values=1,
			max_values=1,
			custom_id=custom_id,
		)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionPickerView):
			return
		if interaction.user.id != view.parent_view.user_id:
			return
		view.selected_role_id = self.values[0].id
		view._build_items()
		await interaction.response.edit_message(embed=_build_picker_embed(view), view=view)


class _SaveReactionButton(discord.ui.Button):
	def __init__(self, picker: RoleReactionPickerView):
		super().__init__(label="Save", style=discord.ButtonStyle.success, custom_id=f"rr-save-{picker._nonce}")
		self._picker = picker

	async def callback(self, interaction: discord.Interaction) -> None:
		picker = self._picker
		if interaction.user.id != picker.parent_view.user_id:
			return

		if not picker.selected_emoji_raw or not picker.selected_role_id:
			await _send_ephemeral_notice(interaction, "Select an emoji and a role first.")
			return

		normalized_emoji = _normalize_emoji_input(picker.selected_emoji_raw)
		if normalized_emoji is None:
			await _send_ephemeral_notice(
				interaction,
				"Invalid emoji. Use a standard Unicode emoji (like ⚙️) or a shortcode like `:gear:`.",
			)
			return

		state = picker.parent_view.state
		if len(state["reactions"]) >= _MAX_REACTIONS_PER_PANEL:
			await _send_ephemeral_notice(
				interaction,
				f"Panels can have at most {_MAX_REACTIONS_PER_PANEL} role reactions.",
			)
			return

		for existing in state["reactions"]:
			if _emoji_matches(str(existing.get("emoji", "")), normalized_emoji):
				await _send_ephemeral_notice(interaction, "That emoji is already used in this panel.")
				return
			if int(existing.get("role_id", 0) or 0) == int(picker.selected_role_id):
				await _send_ephemeral_notice(interaction, "That role is already used in this panel.")
				return

		state["reactions"].append({"emoji": normalized_emoji, "role_id": picker.selected_role_id})

		parent = picker.parent_view
		parent._build_items()
		await interaction.response.edit_message(embed=_build_setup_embed(parent), view=parent)

class RoleReactionSetupView(discord.ui.View):
	def __init__(
		self,
		guild: discord.Guild,
		user_id: int,
		step: int = 1,
		state: Optional[dict] = None,
	):
		super().__init__(timeout=900)
		self.guild = guild
		self.user_id = user_id
		self.step = step
		self.state = state or {
			"panel_name": "Panel name",
			"panel_message": "React to the following emojis to get role.",
			"reactions": [],
			"destination_channel_id": None,
		}
		self._nonce = 0
		self._build_items()

	async def ensure_owner(self, interaction: discord.Interaction) -> bool:
		return interaction.user.id == self.user_id

	def _build_items(self) -> None:
		self._nonce += 1
		self.clear_items()

		if self.step > 1:
			self.add_item(_BackButton())

		if self.step == 1:
			self.add_item(_SetPanelNameButton())
			self.add_item(_ContinueButton())
			self.add_item(_CancelSetupButton())
		elif self.step == 2:
			self.add_item(_SetPanelMessageButton())
			self.add_item(_ContinueButton())
		elif self.step == 3:
			self.add_item(_AddRoleReactionButton())
			self.add_item(_ContinueButton())
		elif self.step == 4:
			self.add_item(_DestinationChannelSelect(custom_id=f"rr-dest-{self._nonce}"))
			self.add_item(_ContinueButton())
		else:
			self.add_item(_ConfirmAndSendButton())

	def next_step(self) -> None:
		self.step = min(5, self.step + 1)
		self._build_items()

	def previous_step(self) -> None:
		self.step = max(1, self.step - 1)
		self._build_items()


class _BackButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		view.previous_step()
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class _CancelSetupButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		home_view = RoleReactionHomeView(view.user_id, view.guild)
		view.stop()
		await interaction.response.edit_message(embed=_build_home_embed(view.guild), view=home_view)


class _SetPanelNameButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set panel name", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.send_modal(PanelNameModal(view))


class _SetPanelMessageButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set panel message", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		await interaction.response.send_modal(PanelMessageModal(view))


class _AddRoleReactionButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Add role reaction", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		picker = RoleReactionPickerView(view, view._nonce)
		await interaction.response.edit_message(embed=_build_picker_embed(picker), view=picker)


class _ContinueButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Save and Continue", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		async def _error(text: str) -> None:
			await _send_ephemeral_notice(interaction, text)

		if view.step == 1 and not str(view.state.get("panel_name", "")).strip():
			await _error("Please set a panel name.")
			return
		if view.step == 3 and not view.state.get("reactions"):
			await _error("Please add at least one role reaction.")
			return
		if view.step == 4 and not view.state.get("destination_channel_id"):
			await _error("Please select a destination channel.")
			return

		view.next_step()
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class _DestinationChannelSelect(discord.ui.ChannelSelect):
	def __init__(self, custom_id: str):
		super().__init__(
			placeholder="Select destination channel",
			channel_types=[discord.ChannelType.text],
			min_values=1,
			max_values=1,
			custom_id=custom_id,
		)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return
		view.state["destination_channel_id"] = self.values[0].id
		await interaction.response.edit_message(embed=_build_setup_embed(view), view=view)


class _ConfirmAndSendButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Confirm and Send Panel", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionSetupView):
			return
		if not await view.ensure_owner(interaction):
			return

		async def _show_error(error_text: str) -> None:
			await _send_ephemeral_notice(interaction, error_text)

		state = view.state
		destination_channel = view.guild.get_channel(int(state.get("destination_channel_id") or 0))
		if not isinstance(destination_channel, discord.TextChannel):
			await _show_error("Destination channel not found. Go back and reselect it.")
			return

		bot_member = view.guild.me
		if bot_member is None:
			await _show_error("Bot member information unavailable. Please try again.")
			return

		perms = destination_channel.permissions_for(bot_member)
		if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.add_reactions):
			await _show_error(
				f"I need **View Channel**, **Send Messages**, **Embed Links**, and **Add Reactions** permissions in "
				f"{destination_channel.mention}."
			)
			return

		reactions = state.get("reactions") or []
		if not reactions:
			await _show_error("Please add at least one role reaction.")
			return

		await interaction.response.defer()

		try:
			panel_message = await destination_channel.send(
				embed=_build_panel_embed(
					state.get("panel_name", "Panel name"),
					state.get("panel_message", "React to the following emojis to get role."),
					view.guild,
					reactions,
				)
			)
		except discord.Forbidden:
			await _show_error(f"Could not post in {destination_channel.mention} — missing permissions.")
			return
		except discord.HTTPException:
			await _show_error(f"Could not post in {destination_channel.mention} due to a Discord API error. Please try again.")
			return

		for item in reactions:
			await _add_panel_reaction(panel_message, str(item.get("emoji", "")))

		panel_id = uuid4().hex[:10]
		panel = {
			"id": panel_id,
			"panel_name": state.get("panel_name", "Panel name"),
			"panel_message": state.get("panel_message", "React to the following emojis to get role."),
			"reactions": reactions,
			"destination_channel_id": int(state.get("destination_channel_id") or 0),
			"panel_channel_id": panel_message.channel.id,
			"panel_message_id": panel_message.id,
		}
		_save_panel(view.guild.id, panel)

		home_view = RoleReactionHomeView(view.user_id, view.guild)
		if interaction.message is not None:
			try:
				await interaction.message.edit(embed=_build_home_embed(view.guild), view=home_view)
			except discord.HTTPException:
				pass

class _ManagePanelSelect(discord.ui.Select):
	def __init__(self, panels: list[dict], selected_id: Optional[str]):
		options = [
			discord.SelectOption(
				label=str(p.get("panel_name", "Panel"))[:100],
				value=str(p.get("id")),
				default=str(p.get("id")) == str(selected_id),
			)
			for p in panels[:25]
		]
		super().__init__(placeholder="Select panel", min_values=1, max_values=1, options=options)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if interaction.user.id != view.user_id:
			return
		view.selected_panel_id = self.values[0]
		view._build_items()
		await interaction.response.edit_message(
			embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id),
			view=view,
		)


class ManagePanelsView(discord.ui.View):
	def __init__(self, guild: discord.Guild, user_id: int, panels: list[dict], selected_id: Optional[str] = None):
		super().__init__(timeout=900)
		self.guild = guild
		self.user_id = user_id
		self.panels = panels
		self.selected_panel_id = selected_id or (str(panels[0].get("id")) if panels else None)
		self._build_items()

	def _get_selected_panel(self) -> Optional[dict]:
		return next(
			(p for p in self.panels if str(p.get("id")) == str(self.selected_panel_id)),
			self.panels[0] if self.panels else None,
		)

	def _build_items(self) -> None:
		self.clear_items()
		if self.panels:
			self.add_item(_ManagePanelSelect(self.panels, self.selected_panel_id))
			self.add_item(_SendPanelAgainButton())
			self.add_item(_DeletePanelButton())
		self.add_item(_ManageBackButton())


class _SendPanelAgainButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Send panel again", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if interaction.user.id != view.user_id:
			return

		panel = view._get_selected_panel()
		if panel is None:
			return

		destination_channel_id = int(panel.get("destination_channel_id", 0) or 0)
		destination_channel = view.guild.get_channel(destination_channel_id)
		if not isinstance(destination_channel, discord.TextChannel):
			await _send_ephemeral_notice(
				interaction,
				"Destination channel not found. You can delete and recreate this panel.",
			)
			return

		bot_member = view.guild.me
		if bot_member is None:
			await _send_ephemeral_notice(interaction, "Bot member information unavailable. Please try again.")
			return

		perms = destination_channel.permissions_for(bot_member)
		if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.add_reactions):
			await _send_ephemeral_notice(
				interaction,
				(
					"I need **View Channel**, **Send Messages**, **Embed Links**, and **Add Reactions** permissions in "
					f"{destination_channel.mention}."
				),
			)
			return

		await interaction.response.defer()

		reactions = panel.get("reactions") or []
		try:
			panel_message = await destination_channel.send(
				embed=_build_panel_embed(
					str(panel.get("panel_name", "Panel name")),
					str(panel.get("panel_message", "React to the following emojis to get role.")),
					view.guild,
					reactions,
				)
			)
		except discord.Forbidden:
			await _send_ephemeral_notice(interaction, f"Could not post in {destination_channel.mention} — missing permissions.")
			return
		except discord.HTTPException:
			await _send_ephemeral_notice(interaction, "Discord API error while sending the panel. Please try again.")
			return

		for item in reactions:
			await _add_panel_reaction(panel_message, str(item.get("emoji", "")))

		panel["panel_channel_id"] = panel_message.channel.id
		panel["panel_message_id"] = panel_message.id
		_save_panel(view.guild.id, panel)
		view.panels = _list_panels(view.guild.id)
		view._build_items()

		if interaction.message is not None:
			await interaction.message.edit(
				embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id),
				view=view,
			)
		await _send_ephemeral_notice(interaction, f"Panel sent to {destination_channel.mention}.")


class _DeletePanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Delete panel", style=discord.ButtonStyle.danger)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if interaction.user.id != view.user_id:
			return

		panel = view._get_selected_panel()
		if panel is None:
			return

		channel_id = int(panel.get("panel_channel_id", 0) or 0)
		message_id = int(panel.get("panel_message_id", 0) or 0)
		target_channel = view.guild.get_channel(channel_id)
		if isinstance(target_channel, discord.TextChannel) and message_id:
			try:
				msg = await target_channel.fetch_message(message_id)
				await msg.delete()
			except Exception:
				pass

		_delete_panel(view.guild.id, str(panel.get("id")))
		view.panels = _list_panels(view.guild.id)
		view.selected_panel_id = str(view.panels[0].get("id")) if view.panels else None
		view._build_items()
		await interaction.response.edit_message(
			embed=_build_manage_embed(view.guild, view.panels, view.selected_panel_id),
			view=view,
		)


class _ManageBackButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ManagePanelsView):
			return
		if interaction.user.id != view.user_id:
			return
		home_view = RoleReactionHomeView(view.user_id, view.guild)
		await interaction.response.edit_message(embed=_build_home_embed(view.guild), view=home_view)

class RoleReactionHomeView(discord.ui.View):
	def __init__(self, user_id: int, guild: discord.Guild):
		super().__init__(timeout=900)
		self.user_id = user_id
		self.guild = guild
		self.add_item(_CreatePanelButton())
		self.add_item(_OpenManagePanelsButton())


class _CreatePanelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Create new panel", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionHomeView):
			return
		if interaction.user.id != view.user_id:
			return
		setup_view = RoleReactionSetupView(view.guild, view.user_id)
		await interaction.response.edit_message(embed=_build_setup_embed(setup_view), view=setup_view)


class _OpenManagePanelsButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Manage panels", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, RoleReactionHomeView):
			return
		if interaction.user.id != view.user_id:
			return
		panels = _list_panels(view.guild.id)
		manage_view = ManagePanelsView(view.guild, view.user_id, panels)
		await interaction.response.edit_message(
			embed=_build_manage_embed(view.guild, panels, manage_view.selected_panel_id),
			view=manage_view,
		)

def _find_role_id_for_emoji(reactions: list[dict], emoji_str: str) -> Optional[int]:
	for item in reactions:
		if _emoji_matches(str(item.get("emoji", "")), emoji_str):
			return int(item.get("role_id"))
	return None


async def handle_raw_reaction_add(bot, payload: discord.RawReactionActionEvent) -> None:
	if payload.guild_id is None or payload.user_id == bot.user.id:
		return

	guild = bot.get_guild(payload.guild_id)
	if guild is None:
		return

	panel = _get_panel_by_message_id(guild.id, payload.message_id)
	if panel is None:
		return

	matching_role_id = _find_role_id_for_emoji(panel.get("reactions", []), str(payload.emoji))
	if matching_role_id is None:
		return

	try:
		member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
	except (discord.NotFound, discord.Forbidden, discord.HTTPException):
		return
	if member is None:
		return

	role = guild.get_role(int(matching_role_id))
	if role is None:
		return

	try:
		await member.add_roles(role, reason="Role reaction panel")
	except discord.Forbidden:
		logging.warning("Missing permission to add role %s to member %s", role.name, member.id)


async def handle_raw_reaction_remove(bot, payload: discord.RawReactionActionEvent) -> None:
	if payload.guild_id is None or payload.user_id == bot.user.id:
		return

	guild = bot.get_guild(payload.guild_id)
	if guild is None:
		return

	panel = _get_panel_by_message_id(guild.id, payload.message_id)
	if panel is None:
		return

	matching_role_id = _find_role_id_for_emoji(panel.get("reactions", []), str(payload.emoji))
	if matching_role_id is None:
		return

	try:
		member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
	except (discord.NotFound, discord.Forbidden, discord.HTTPException):
		return
	if member is None:
		return

	role = guild.get_role(int(matching_role_id))
	if role is None:
		return

	try:
		await member.remove_roles(role, reason="Role reaction panel")
	except discord.Forbidden:
		logging.warning("Missing permission to remove role %s from member %s", role.name, member.id)

async def handle_role_reaction_setup(interaction: discord.Interaction) -> None:
	if interaction.guild is None:
		await interaction.response.send_message(
			"This command can only be used inside a server.",
			ephemeral=True,
		)
		return

	if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
		await interaction.response.send_message(
			"You don't have permission to use this command.",
			ephemeral=True,
		)
		return

	home_view = RoleReactionHomeView(interaction.user.id, interaction.guild)
	await interaction.response.send_message(embed=_build_home_embed(interaction.guild), view=home_view)

