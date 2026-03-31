from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import discord

import comp_builder
import guild_settings
import globals


_OBJECTIVES_FILE = Path("configs/objectives_config.json")

_OBJECTIVE_TYPE_VORTEX = "Vortex"
_OBJECTIVE_TYPE_CORE = "Core"
_OBJECTIVE_TYPE_NODE = "Node"

_VORTEX_RARITIES = ["Common", "Uncommon", "Epic", "Legendary"]
_NODE_TYPES = ["Wood", "Hide", "Ore", "Fiber"]
_NODE_TIERS = ["4.4", "5.4", "6.4", "7.4", "8.4"]

_VORTEX_RARITY_EMOJI = {
	"Common": "🟢",
	"Uncommon": "🔵",
	"Epic": "🟣",
	"Legendary": "🟡",
}


def _vortex_rarity_display(rarity: Optional[str]) -> str:
	value = (rarity or "").strip()
	if not value:
		return "Not selected yet"
	emoji_char = _VORTEX_RARITY_EMOJI.get(value)
	if not emoji_char:
		return value
	return f"{emoji_char} {value} {emoji_char}"


_NOTIFY_BEFORE_MINUTES_OPTIONS = list(range(5, 61, 5))


def _notify_before_display(minutes: Optional[int]) -> str:
	try:
		minutes_int = int(minutes) if minutes is not None else 0
	except (TypeError, ValueError):
		minutes_int = 0
	if minutes_int in _NOTIFY_BEFORE_MINUTES_OPTIONS:
		return f"{minutes_int} minutes"
	return "Not selected yet"

_OBJECTIVE_EXPIRY_SECONDS = 60
_SCHEDULER_INTERVAL_SECONDS = 10

_scheduler_task: Optional[asyncio.Task] = None


def _load_config() -> dict:
	if not _OBJECTIVES_FILE.exists():
		return {}

	try:
		with _OBJECTIVES_FILE.open("r", encoding="utf-8") as file:
			data = json.load(file)
	except (json.JSONDecodeError, OSError):
		return {}

	return data if isinstance(data, dict) else {}


def _save_config(config: dict) -> None:
	_OBJECTIVES_FILE.parent.mkdir(parents=True, exist_ok=True)
	with _OBJECTIVES_FILE.open("w", encoding="utf-8") as file:
		json.dump(config, file, ensure_ascii=True, indent=2)


def _guild_entry(config: dict, guild_id: int) -> dict:
	key = str(guild_id)
	if not isinstance(config.get(key), dict):
		config[key] = {}
	entry = config[key]
	entry.setdefault("panel_channel_id", None)
	entry.setdefault("panel_message_id", None)
	entry.setdefault("objectives", [])
	if not isinstance(entry.get("objectives"), list):
		entry["objectives"] = []
	return entry


def get_objectives_panel_message(guild_id: int) -> tuple[Optional[int], Optional[int]]:
	config = _load_config()
	entry = config.get(str(guild_id))
	if not isinstance(entry, dict):
		return None, None

	try:
		channel_id = int(entry.get("panel_channel_id")) if entry.get("panel_channel_id") else None
		message_id = int(entry.get("panel_message_id")) if entry.get("panel_message_id") else None
	except (TypeError, ValueError):
		return None, None

	return channel_id, message_id


def set_objectives_panel_message(guild_id: int, channel_id: int, message_id: int) -> None:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	entry["panel_channel_id"] = str(channel_id)
	entry["panel_message_id"] = str(message_id)
	_save_config(config)


def list_objectives(guild_id: int) -> list[dict]:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.get("objectives", [])
	return objectives if isinstance(objectives, list) else []


def add_objective(guild_id: int, objective: dict) -> None:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.setdefault("objectives", [])
	if not isinstance(objectives, list):
		objectives = []
		entry["objectives"] = objectives
	objectives.append(objective)
	_save_config(config)


def _update_objective(guild_id: int, objective: dict) -> None:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.get("objectives", [])
	if not isinstance(objectives, list):
		return

	obj_id = objective.get("id")
	if not obj_id:
		return

	for idx, item in enumerate(objectives):
		if isinstance(item, dict) and item.get("id") == obj_id:
			objectives[idx] = objective
			_save_config(config)
			return


def _build_panel_embed(guild: discord.Guild) -> discord.Embed:
	return discord.Embed(title="Active objectives:")


def _format_objective_name(obj: dict) -> str:
	obj_type = (obj.get("type") or "").strip()
	if obj_type == _OBJECTIVE_TYPE_VORTEX:
		rarity = _vortex_rarity_display(obj.get("rarity"))
		map_name = obj.get("map") or "Unknown map"
		return f"🌀 Vortex ({rarity}) — {map_name}"
	if obj_type == _OBJECTIVE_TYPE_CORE:
		rarity = _vortex_rarity_display(obj.get("rarity"))
		map_name = obj.get("map") or "Unknown map"
		return f"🔷 Core ({rarity}) — {map_name}"
	if obj_type == _OBJECTIVE_TYPE_NODE:
		node_type = (obj.get("node_type") or "Node").strip() or "Node"
		tier = obj.get("tier") or "?"
		map_name = obj.get("map") or "Unknown map"
		return f"⛏️ {node_type} ({tier}) — {map_name}"
	return "Objective"

def _format_pop_time(pop_at_ts: int, pop_time_utc_hhmm: Optional[str]) -> str:
	if not pop_at_ts:
		return "Time not set yet"
	time_label = (pop_time_utc_hhmm or "").strip() or "??:??"
	return f"Pops in <t:{pop_at_ts}:R>, at {time_label} UTC"


def _build_objective_embed(obj: dict) -> discord.Embed:
	obj_type = obj.get("type")
	title = "Objective"
	if obj_type == _OBJECTIVE_TYPE_VORTEX:
		title = f"🌀 Vortex ({_vortex_rarity_display(obj.get('rarity'))})"
	elif obj_type == _OBJECTIVE_TYPE_CORE:
		title = f"🔷 Core ({_vortex_rarity_display(obj.get('rarity'))})"
	elif obj_type == _OBJECTIVE_TYPE_NODE:
		title = f"⛏️ Node ({obj.get('node_type', 'Unknown')} {obj.get('tier', '?')})"

	embed = discord.Embed(title=title)
	embed.add_field(name="Map", value=obj.get("map") or "Not set", inline=False)
	pop_at_ts = int(obj.get("pop_at_ts") or 0)
	remove_at_ts = int(obj.get("remove_at_ts") or 0)
	if remove_at_ts:
		name = _format_objective_name(obj)
		embed.add_field(
			name="Pop time",
			value=f"{name} has already popped up, it will be removed soon.",
			inline=False,
		)
	else:
		embed.add_field(name="Pop time", value=_format_pop_time(pop_at_ts, obj.get("pop_time_utc")), inline=False)
	notify_before = obj.get("notify_before_minutes")
	embed.add_field(
		name="Notify before pop",
		value=_notify_before_display(notify_before),
		inline=False,
	)
	created_by = obj.get("created_by")
	created_by_id = obj.get("created_by_id")
	added_by_value: Optional[str] = None
	if created_by_id:
		try:
			created_by_id_int = int(created_by_id)
		except (TypeError, ValueError):
			created_by_id_int = None
		if created_by_id_int:
			added_by_value = f"<@{created_by_id_int}>"
	if not added_by_value and created_by:
		added_by_value = str(created_by)
	if added_by_value:
		embed.add_field(name="Added by", value=added_by_value, inline=False)
	return embed


def start_objectives_scheduler(bot: discord.Client) -> None:
	global _scheduler_task
	if _scheduler_task is not None and not _scheduler_task.done():
		return
	_scheduler_task = bot.loop.create_task(_objectives_scheduler_loop(bot))


async def _objectives_scheduler_loop(bot: discord.Client) -> None:
	while True:
		try:
			now_ts = int(datetime.now(timezone.utc).timestamp())
			await _process_all_guilds(bot, now_ts)
		except Exception:
			logging.exception("Objectives scheduler tick failed")
		await asyncio.sleep(_SCHEDULER_INTERVAL_SECONDS)


async def _process_all_guilds(bot: discord.Client, now_ts: int) -> None:
	config = _load_config()

	for guild_id_str, entry in list(config.items()):
		if not isinstance(entry, dict):
			continue
		try:
			guild_id = int(guild_id_str)
		except ValueError:
			continue

		guild = bot.get_guild(guild_id)
		if guild is None:
			continue

		(
			popped_remove_at_by_key,
			notified_ts_by_key,
			notify_message_id_by_key,
			cleared_notify_assets_keys,
			remove_keys,
			needs_panel_refresh,
		) = await _process_guild(
			guild,
			entry,
			now_ts,
		)
		if (
			popped_remove_at_by_key
			or notified_ts_by_key
			or notify_message_id_by_key
			or cleared_notify_assets_keys
			or remove_keys
		):
			_apply_objective_deltas(
				guild_id,
				popped_remove_at_by_key,
				notified_ts_by_key,
				notify_message_id_by_key,
				cleared_notify_assets_keys,
				remove_keys,
			)
		if needs_panel_refresh:
			panel_channel_id, panel_message_id = get_objectives_panel_message(guild_id)
			if panel_channel_id and panel_message_id:
				await _refresh_panel_message(guild, panel_channel_id, panel_message_id)


def _objective_key(obj: dict) -> str:
	"""Return the best stable identifier for matching objectives in config."""
	obj_id = (obj.get("id") or "").strip()
	if obj_id:
		return f"id:{obj_id}"
	try:
		msg_id = int(obj.get("message_id") or 0)
	except (TypeError, ValueError):
		msg_id = 0
	if msg_id:
		return f"msg:{msg_id}"
	return ""


def _apply_objective_deltas(
	guild_id: int,
	popped_remove_at_by_key: dict[str, int],
	notified_ts_by_key: dict[str, int],
	notify_message_id_by_key: dict[str, int],
	cleared_notify_assets_keys: set[str],
	remove_keys: set[str],
) -> None:
	"""Apply scheduler changes to the *latest* config to avoid clobbering concurrent writes."""
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.get("objectives", [])
	if not isinstance(objectives, list) or not objectives:
		return

	new_objectives: list[dict] = []
	for obj in objectives:
		if not isinstance(obj, dict):
			continue
		key = _objective_key(obj)
		if key and key in remove_keys:
			continue
		if key and key in popped_remove_at_by_key:
			obj["remove_at_ts"] = int(popped_remove_at_by_key[key])
		if key and key in notified_ts_by_key:
			obj["notified_ts"] = int(notified_ts_by_key[key])
		if key and key in notify_message_id_by_key:
			obj["notify_message_id"] = int(notify_message_id_by_key[key])
		if key and key in cleared_notify_assets_keys:
			obj.pop("notify_role_id", None)
			obj.pop("notify_message_id", None)
		new_objectives.append(obj)

	entry["objectives"] = new_objectives
	_save_config(config)


async def _process_guild(
	guild: discord.Guild,
	entry: dict,
	now_ts: int,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], set[str], set[str], bool]:
	objectives = entry.get("objectives")
	if not isinstance(objectives, list) or not objectives:
		return {}, {}, {}, set(), set(), False

	panel_channel_id = entry.get("panel_channel_id")
	try:
		panel_channel_id_int = int(panel_channel_id) if panel_channel_id else None
	except (TypeError, ValueError):
		panel_channel_id_int = None

	popped_remove_at_by_key: dict[str, int] = {}
	notified_ts_by_key: dict[str, int] = {}
	notify_message_id_by_key: dict[str, int] = {}
	cleared_notify_assets_keys: set[str] = set()
	remove_keys: set[str] = set()
	needs_panel_refresh = False

	for obj in list(objectives):
		if not isinstance(obj, dict):
			continue

		key = _objective_key(obj)

		pop_at_ts = int(obj.get("pop_at_ts") or 0)
		remove_at_ts = int(obj.get("remove_at_ts") or 0)
		notified_ts = int(obj.get("notified_ts") or 0)

		notify_before_minutes = obj.get("notify_before_minutes")
		try:
			notify_before_minutes_int = int(notify_before_minutes) if notify_before_minutes is not None else 0
		except (TypeError, ValueError):
			notify_before_minutes_int = 0

		if (
			notify_before_minutes_int in _NOTIFY_BEFORE_MINUTES_OPTIONS
			and pop_at_ts
			and not remove_at_ts
			and not notified_ts
		):
			notify_at_ts = int(obj.get("notify_at_ts") or (pop_at_ts - notify_before_minutes_int * 60))
			if notify_at_ts > 0 and now_ts >= notify_at_ts and now_ts < pop_at_ts:
				notify_msg_id = await _send_objective_notification(
					guild,
					obj,
					panel_channel_id_int,
					notify_before_minutes_int,
				)
				if notify_msg_id:
					obj["notified_ts"] = int(now_ts)
					if key:
						notified_ts_by_key[key] = int(now_ts)
						notify_message_id_by_key[key] = int(notify_msg_id)

		# If the objective already popped (remove_at_ts set) but notify assets still exist,
		# keep trying to clean them up until the objective is removed.
		if pop_at_ts and now_ts >= pop_at_ts and remove_at_ts and (
			obj.get("notify_role_id") or obj.get("notify_message_id")
		):
			if await _cleanup_objective_notification_assets(guild, obj, panel_channel_id_int):
				if key:
					cleared_notify_assets_keys.add(key)

		if remove_at_ts and now_ts >= remove_at_ts:
			await _delete_objective_message(guild, obj, panel_channel_id_int)
			if key:
				remove_keys.add(key)
			needs_panel_refresh = True
			continue

		if pop_at_ts and now_ts >= pop_at_ts and not remove_at_ts:
			new_remove_at = now_ts + _OBJECTIVE_EXPIRY_SECONDS
			obj["remove_at_ts"] = new_remove_at
			if key:
				popped_remove_at_by_key[key] = int(new_remove_at)
			needs_panel_refresh = True
			if await _cleanup_objective_notification_assets(guild, obj, panel_channel_id_int):
				if key:
					cleared_notify_assets_keys.add(key)
			await _mark_objective_popped(guild, obj, panel_channel_id_int)

	return (
		popped_remove_at_by_key,
		notified_ts_by_key,
		notify_message_id_by_key,
		cleared_notify_assets_keys,
		remove_keys,
		needs_panel_refresh,
	)


async def _send_objective_notification(
	guild: discord.Guild,
	obj: dict,
	fallback_channel_id: Optional[int],
	notify_before_minutes: int,
) -> Optional[int]:
	role_id = obj.get("notify_role_id")
	try:
		role_id_int = int(role_id) if role_id else None
	except (TypeError, ValueError):
		role_id_int = None
	if not role_id_int:
		return None

	channel_id = obj.get("channel_id") or fallback_channel_id
	try:
		channel_id_int = int(channel_id) if channel_id else None
	except (TypeError, ValueError):
		channel_id_int = None
	if not channel_id_int:
		return None

	try:
		ch = guild.get_channel(channel_id_int)
		if ch is None:
			ch = await guild.fetch_channel(channel_id_int)
		if not isinstance(ch, discord.TextChannel):
			return None
		pop_at_ts = int(obj.get("pop_at_ts") or 0)
		pop_part = _format_pop_time(pop_at_ts, obj.get("pop_time_utc"))
		content = f"<@&{role_id_int}> {_format_objective_name(obj)}. {pop_part}"
		sent = await ch.send(content, allowed_mentions=discord.AllowedMentions(roles=True))
		return int(sent.id)
	except (discord.Forbidden, discord.HTTPException, discord.NotFound):
		return None


async def _cleanup_objective_notification_assets(
	guild: discord.Guild,
	obj: dict,
	fallback_channel_id: Optional[int],
) -> bool:
	"""Delete notify role + notify ping message (if any). Returns True if fully cleaned or already missing."""
	all_clean = True

	# Delete the notification ping message.
	notify_message_id = obj.get("notify_message_id")
	objective_message_id = obj.get("message_id")
	try:
		notify_message_id_int = int(notify_message_id) if notify_message_id else None
	except (TypeError, ValueError):
		notify_message_id_int = None
	try:
		objective_message_id_int = int(objective_message_id) if objective_message_id else None
	except (TypeError, ValueError):
		objective_message_id_int = None

	if notify_message_id_int and notify_message_id_int != objective_message_id_int:
		channel_id = obj.get("channel_id") or fallback_channel_id
		try:
			channel_id_int = int(channel_id) if channel_id else None
		except (TypeError, ValueError):
			channel_id_int = None
		if channel_id_int:
			try:
				ch = guild.get_channel(channel_id_int)
				if ch is None:
					ch = await guild.fetch_channel(channel_id_int)
				if isinstance(ch, discord.TextChannel):
					msg = await ch.fetch_message(notify_message_id_int)
					await msg.delete()
					obj.pop("notify_message_id", None)
			except discord.NotFound:
				obj.pop("notify_message_id", None)
			except (discord.Forbidden, discord.HTTPException):
				all_clean = False

	# Delete the notification role.
	role_id = obj.get("notify_role_id")
	try:
		role_id_int = int(role_id) if role_id else None
	except (TypeError, ValueError):
		role_id_int = None
	if role_id_int:
		role = guild.get_role(role_id_int)
		if role is None:
			obj.pop("notify_role_id", None)
		else:
			try:
				await role.delete(reason="Objective popped")
				obj.pop("notify_role_id", None)
			except (discord.Forbidden, discord.HTTPException):
				all_clean = False

	return all_clean


async def _refresh_panel_message(guild: discord.Guild, channel_id: int, message_id: int) -> None:
	try:
		ch = guild.get_channel(channel_id)
		if ch is None:
			ch = await guild.fetch_channel(channel_id)
		if not isinstance(ch, discord.TextChannel):
			return
		msg = await ch.fetch_message(message_id)
		await msg.edit(embed=_build_panel_embed(guild), view=ObjectivesPanelView())
	except (discord.NotFound, discord.Forbidden, discord.HTTPException):
		return


async def _mark_objective_popped(guild: discord.Guild, obj: dict, fallback_channel_id: Optional[int]) -> None:
	await _edit_objective_message(guild, obj, fallback_channel_id)


async def _edit_objective_message(guild: discord.Guild, obj: dict, fallback_channel_id: Optional[int]) -> None:
	message_id = obj.get("message_id")
	channel_id = obj.get("channel_id") or fallback_channel_id
	try:
		message_id_int = int(message_id) if message_id else None
		channel_id_int = int(channel_id) if channel_id else None
	except (TypeError, ValueError):
		return

	if not message_id_int or not channel_id_int:
		return

	try:
		ch = guild.get_channel(channel_id_int)
		if ch is None:
			ch = await guild.fetch_channel(channel_id_int)
		if not isinstance(ch, discord.TextChannel):
			return
		msg = await ch.fetch_message(message_id_int)
		await msg.edit(embed=_build_objective_embed(obj), view=ObjectiveMessageView())
	except (discord.NotFound, discord.Forbidden, discord.HTTPException):
		return


async def _delete_objective_message(guild: discord.Guild, obj: dict, fallback_channel_id: Optional[int]) -> None:
	message_id = obj.get("message_id")
	channel_id = obj.get("channel_id") or fallback_channel_id
	try:
		message_id_int = int(message_id) if message_id else None
		channel_id_int = int(channel_id) if channel_id else None
	except (TypeError, ValueError):
		return

	if not message_id_int or not channel_id_int:
		return

	try:
		ch = guild.get_channel(channel_id_int)
		if ch is None:
			ch = await guild.fetch_channel(channel_id_int)
		if not isinstance(ch, discord.TextChannel):
			return
		msg = await ch.fetch_message(message_id_int)
		await msg.delete()
	except (discord.NotFound, discord.Forbidden, discord.HTTPException):
		return


async def _send_ephemeral_notice(interaction: discord.Interaction, text: str) -> None:
	if interaction.response.is_done():
		await interaction.followup.send(text, ephemeral=True)
	else:
		await interaction.response.send_message(text, ephemeral=True)


async def post_or_update_objectives_panel(
	guild: discord.Guild,
	channel: discord.abc.Messageable,
) -> tuple[bool, str]:
	embed = _build_panel_embed(guild)
	panel_channel_id, panel_message_id = get_objectives_panel_message(guild.id)

	target_channel_id = getattr(channel, "id", None)
	if not isinstance(target_channel_id, int):
		target_channel_id = None

	if panel_channel_id and panel_message_id:
		if target_channel_id is not None and int(panel_channel_id) == int(target_channel_id):
			try:
				existing_channel = guild.get_channel(panel_channel_id)
				if existing_channel is None:
					existing_channel = await guild.fetch_channel(panel_channel_id)

				if isinstance(existing_channel, discord.TextChannel):
					existing_message = await existing_channel.fetch_message(panel_message_id)
					await existing_message.edit(embed=embed, view=ObjectivesPanelView())
					return True, "Objectives panel updated."
			except discord.NotFound:
				pass
			except discord.Forbidden:
				return False, "Missing permission to update the existing objectives panel."
			except discord.HTTPException:
				return False, "Failed to update the existing objectives panel."

		try:
			old_channel = guild.get_channel(panel_channel_id)
			if old_channel is None:
				old_channel = await guild.fetch_channel(panel_channel_id)
			if isinstance(old_channel, discord.TextChannel):
				try:
					old_message = await old_channel.fetch_message(panel_message_id)
					try:
						await old_message.delete()
					except discord.Forbidden:
						await old_message.edit(
							content="(Objectives panel moved to another channel.)",
							embed=None,
							view=None,
						)
				except discord.NotFound:
					pass
		except (discord.Forbidden, discord.HTTPException):
			pass

	try:
		sent = await channel.send(embed=embed, view=ObjectivesPanelView())
	except discord.Forbidden:
		return False, "Missing permission to send messages in this channel."
	except discord.HTTPException:
		return False, "Failed to send objectives panel."

	sent_channel_id = getattr(sent.channel, "id", None)
	if isinstance(sent_channel_id, int):
		set_objectives_panel_message(guild.id, sent_channel_id, sent.id)
	return True, "Objectives panel posted."


async def handle_set_objectivess_panel(interaction: discord.Interaction) -> None:
	if interaction.guild is None or interaction.channel is None:
		await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
		return

	if not guild_settings.get_target_guild(interaction.guild.id):
		await interaction.response.send_message(
			"This server is not configured yet. Run **/bot-setup** first.",
			ephemeral=True,
		)
		return

	if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
		await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
		return

	ok, message = await post_or_update_objectives_panel(interaction.guild, interaction.channel)
	await interaction.response.send_message(message if ok else f"Error: {message}", ephemeral=True)


class ObjectivesPanelView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)
		self.add_item(_AddObjectiveButton())


class _AddObjectiveButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Add Objective", style=discord.ButtonStyle.primary, custom_id="obj:add")

	async def callback(self, interaction: discord.Interaction) -> None:
		if interaction.guild is None:
			await _send_ephemeral_notice(interaction, "This can only be used inside a server.")
			return

		view = ObjectiveWizardView(interaction.user.id)
		embed = _build_wizard_embed(view)
		if interaction.response.is_done():
			await interaction.followup.send(embed=embed, view=view, ephemeral=True)
		else:
			await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


def register_persistent_views(bot) -> None:
	bot.add_view(ObjectivesPanelView())
	bot.add_view(ObjectiveMessageView())


class ObjectiveMessageView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)
		self.add_item(_NotifyMeButton())
		self.add_item(_RemoveObjectiveButton())


def _find_objective_by_message_id(guild_id: int, message_id: int) -> Optional[dict]:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.get("objectives", [])
	if not isinstance(objectives, list) or not objectives:
		return None

	for obj in objectives:
		if not isinstance(obj, dict):
			continue
		try:
			obj_msg_id = int(obj.get("message_id") or 0)
		except (TypeError, ValueError):
			obj_msg_id = 0
		if obj_msg_id == int(message_id):
			return obj

	return None


class _NotifyMeButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Notify Me", style=discord.ButtonStyle.primary, custom_id="obj:notifyme")

	async def callback(self, interaction: discord.Interaction) -> None:
		if interaction.guild is None:
			await _send_ephemeral_notice(interaction, "This can only be used inside a server.")
			return

		if not isinstance(interaction.user, discord.Member):
			await _send_ephemeral_notice(interaction, "Unable to assign roles for this user.")
			return

		if interaction.message is None:
			await _send_ephemeral_notice(interaction, "Unable to locate objective message.")
			return

		objective = _find_objective_by_message_id(interaction.guild.id, interaction.message.id)
		if not objective:
			await _send_ephemeral_notice(interaction, "Objective not found (it may have been removed already).")
			return

		role_id = objective.get("notify_role_id")
		try:
			role_id_int = int(role_id) if role_id else None
		except (TypeError, ValueError):
			role_id_int = None
		if not role_id_int:
			await _send_ephemeral_notice(
				interaction,
				"This objective has no notification role (role creation may have failed).",
			)
			return

		role = interaction.guild.get_role(role_id_int)
		if role is None:
			await _send_ephemeral_notice(interaction, "Notification role not found on this server.")
			return

		try:
			await interaction.user.add_roles(role, reason="Objective notify-me")
		except discord.Forbidden:
			await _send_ephemeral_notice(
				interaction,
				"Missing permission to assign that role. Make sure the bot has Manage Roles and is above the role.",
			)
			return
		except discord.HTTPException:
			await _send_ephemeral_notice(interaction, "Failed to assign notification role.")
			return

		await _send_ephemeral_notice(interaction, "Done. You will be pinged before this objective pops.")


class _RemoveObjectiveButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Remove Objective", style=discord.ButtonStyle.danger, custom_id="obj:remove")

	async def callback(self, interaction: discord.Interaction) -> None:
		if interaction.guild is None:
			await _send_ephemeral_notice(interaction, "This can only be used inside a server.")
			return

		if not isinstance(interaction.user, discord.Member):
			await _send_ephemeral_notice(interaction, "You don't have permission to remove objectives.")
			return

		caller_roles = guild_settings.get_caller_roles(interaction.guild.id)
		if not comp_builder.has_caller_access(interaction.user, caller_roles):
			await _send_ephemeral_notice(interaction, "You don't have permission to remove objectives.")
			return

		if interaction.message is None:
			await _send_ephemeral_notice(interaction, "Unable to locate objective message.")
			return

		removed = _remove_objective_by_message_id(interaction.guild.id, interaction.message.id)
		if not removed:
			await _send_ephemeral_notice(interaction, "Objective not found (it may have been removed already).")
			return

		try:
			await interaction.message.delete()
		except (discord.Forbidden, discord.HTTPException):
			pass

		channel_id, message_id = get_objectives_panel_message(interaction.guild.id)
		if channel_id and message_id:
			await _refresh_panel_message(interaction.guild, channel_id, message_id)

		await _send_ephemeral_notice(interaction, "Objective removed.")


def _remove_objective_by_message_id(guild_id: int, message_id: int) -> bool:
	config = _load_config()
	entry = _guild_entry(config, guild_id)
	objectives = entry.get("objectives", [])
	if not isinstance(objectives, list) or not objectives:
		return False

	for obj in list(objectives):
		if not isinstance(obj, dict):
			continue
		try:
			obj_msg_id = int(obj.get("message_id") or 0)
		except (TypeError, ValueError):
			obj_msg_id = 0
		if obj_msg_id == int(message_id):
			try:
				objectives.remove(obj)
			except ValueError:
				pass
			entry["objectives"] = objectives
			_save_config(config)
			return True

	return False


@dataclass
class _WizardState:
	objective_type: Optional[str] = None
	vortex_rarity: Optional[str] = None
	node_type: Optional[str] = None
	node_tier: Optional[str] = None
	pop_time_utc: Optional[str] = None
	pop_at_ts: Optional[int] = None
	map_name: Optional[str] = None
	notify_before_minutes: Optional[int] = None


class ObjectiveWizardView(discord.ui.View):
	def __init__(self, user_id: int):
		super().__init__(timeout=600)
		self.user_id = user_id
		self.step = 1
		self.state = _WizardState()
		self._build_items()

	def _total_steps(self) -> int:
		if self.state.objective_type == _OBJECTIVE_TYPE_NODE:
			return 7
		if self.state.objective_type in (_OBJECTIVE_TYPE_VORTEX, _OBJECTIVE_TYPE_CORE):
			return 6
		return 1

	def _build_items(self) -> None:
		self.clear_items()

		if self.step == 1:
			self.add_item(_ObjectiveTypeSelect())
			self.add_item(_WizardSaveContinueButton())
			self.add_item(_WizardCancelButton())
			return

		if self.state.objective_type == _OBJECTIVE_TYPE_VORTEX:
			self._build_vortex_items()
		elif self.state.objective_type == _OBJECTIVE_TYPE_CORE:
			self._build_core_items()
		elif self.state.objective_type == _OBJECTIVE_TYPE_NODE:
			self._build_node_items()
		else:
			self.step = 1
			self._build_items()

	def _build_core_items(self) -> None:
		if self.step == 2:
			self.add_item(_WizardBackButton())
			self.add_item(_CoreRaritySelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 3:
			self.add_item(_WizardBackButton())
			self.add_item(_SetPopTimeButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 4:
			self.add_item(_WizardBackButton())
			self.add_item(_SetMapButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 5:
			self.add_item(_WizardBackButton())
			self.add_item(_NotifyBeforeSelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 6:
			self.add_item(_WizardBackButton())
			self.add_item(_WizardConfirmButton())
			self.add_item(_WizardCancelButton())
			return

		self.step = 1
		self._build_items()

	def _build_vortex_items(self) -> None:
		if self.step == 2:
			self.add_item(_WizardBackButton())
			self.add_item(_VortexRaritySelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 3:
			self.add_item(_WizardBackButton())
			self.add_item(_SetPopTimeButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 4:
			self.add_item(_WizardBackButton())
			self.add_item(_SetMapButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 5:
			self.add_item(_WizardBackButton())
			self.add_item(_NotifyBeforeSelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 6:
			self.add_item(_WizardBackButton())
			self.add_item(_WizardConfirmButton())
			self.add_item(_WizardCancelButton())
			return

		self.step = 1
		self._build_items()

	def _build_node_items(self) -> None:
		if self.step == 2:
			self.add_item(_WizardBackButton())
			self.add_item(_NodeTypeSelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 3:
			self.add_item(_WizardBackButton())
			self.add_item(_NodeTierSelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 4:
			self.add_item(_WizardBackButton())
			self.add_item(_SetPopTimeButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 5:
			self.add_item(_WizardBackButton())
			self.add_item(_SetMapButton())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 6:
			self.add_item(_WizardBackButton())
			self.add_item(_NotifyBeforeSelect())
			self.add_item(_WizardSaveContinueButton())
			return

		if self.step == 7:
			self.add_item(_WizardBackButton())
			self.add_item(_WizardConfirmButton())
			self.add_item(_WizardCancelButton())
			return

		self.step = 1
		self._build_items()


def _build_wizard_embed(view: ObjectiveWizardView) -> discord.Embed:
	total_steps = view._total_steps()
	step = view.step
	embed = discord.Embed(title=f"Add Objective — Step {step}/{total_steps}")

	if step == 1:
		embed.description = "## :dart: Select objective type"
		embed.add_field(
			name="Selected type",
			value=view.state.objective_type or "Not selected yet",
			inline=False,
		)
		return embed

	if view.state.objective_type == _OBJECTIVE_TYPE_VORTEX:
		if step == 2:
			embed.description = "## :sparkles: Select vortex rarity"
			embed.add_field(
				name="Selected rarity",
				value=_vortex_rarity_display(view.state.vortex_rarity),
				inline=False,
			)
		elif step == 3:
			embed.description = "## :alarm_clock: Set pop time in UTC"
			embed.add_field(
				name="Pop time preview",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		elif step == 4:
			embed.description = "## :map: Set objective map"
			embed.add_field(
				name="Map preview",
				value=view.state.map_name or "Map not set yet",
				inline=False,
			)
		elif step == 5:
			embed.description = "## :bell: Notify before objective pop"
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
		else:
			embed.description = "## :clipboard: Final objective preview and confirmation"
			embed.add_field(name="Type", value=_OBJECTIVE_TYPE_VORTEX, inline=True)
			embed.add_field(name="Rarity", value=_vortex_rarity_display(view.state.vortex_rarity), inline=True)
			embed.add_field(name="Map", value=view.state.map_name or "Map not set yet", inline=False)
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
			embed.add_field(
				name="Pop time",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		return embed

	if view.state.objective_type == _OBJECTIVE_TYPE_CORE:
		if step == 2:
			embed.description = "## :sparkles: Select core rarity"
			embed.add_field(
				name="Selected rarity",
				value=_vortex_rarity_display(view.state.vortex_rarity),
				inline=False,
			)
		elif step == 3:
			embed.description = "## :alarm_clock: Set pop time in UTC"
			embed.add_field(
				name="Pop time preview",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		elif step == 4:
			embed.description = "## :map: Set objective map"
			embed.add_field(
				name="Map preview",
				value=view.state.map_name or "Map not set yet",
				inline=False,
			)
		elif step == 5:
			embed.description = "## :bell: Notify before objective pop"
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
		else:
			embed.description = "## :clipboard: Final objective preview and confirmation"
			embed.add_field(name="Type", value=_OBJECTIVE_TYPE_CORE, inline=True)
			embed.add_field(name="Rarity", value=_vortex_rarity_display(view.state.vortex_rarity), inline=True)
			embed.add_field(name="Map", value=view.state.map_name or "Map not set yet", inline=False)
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
			embed.add_field(
				name="Pop time",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		return embed

	if view.state.objective_type == _OBJECTIVE_TYPE_NODE:
		if step == 2:
			embed.description = "## :sparkles: Select node type"
			embed.add_field(name="Selected type", value=view.state.node_type or "Not selected yet", inline=False)
		elif step == 3:
			embed.description = "## :sparkles: Select node tier"
			embed.add_field(name="Selected tier", value=view.state.node_tier or "Not selected yet", inline=False)
		elif step == 4:
			embed.description = "## :alarm_clock: Set pop time in UTC"
			embed.add_field(
				name="Pop time preview",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		elif step == 5:
			embed.description = "## :map: Set objective map"
			embed.add_field(name="Map preview", value=view.state.map_name or "Map not set yet", inline=False)
		elif step == 6:
			embed.description = "## :bell: Notify before objective pop"
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
		else:
			embed.description = "## :clipboard: Final objective preview and confirmation"
			embed.add_field(name="Type", value=_OBJECTIVE_TYPE_NODE, inline=True)
			embed.add_field(name="Node", value=view.state.node_type or "Not selected yet", inline=True)
			embed.add_field(name="Tier", value=view.state.node_tier or "Not selected yet", inline=True)
			embed.add_field(name="Map", value=view.state.map_name or "Map not set yet", inline=False)
			embed.add_field(
				name="Notify before pop",
				value=_notify_before_display(view.state.notify_before_minutes),
				inline=False,
			)
			embed.add_field(
				name="Pop time",
				value=_format_pop_time(view.state.pop_at_ts or 0, view.state.pop_time_utc)
				if view.state.pop_time_utc
				else "Time not set yet",
				inline=False,
			)
		return embed

	embed.description = "## :dart: Select objective type"
	return embed


class _ObjectiveTypeSelect(discord.ui.Select):
	def __init__(self):
		options = [
			discord.SelectOption(label=_OBJECTIVE_TYPE_VORTEX, value=_OBJECTIVE_TYPE_VORTEX),
			discord.SelectOption(label=_OBJECTIVE_TYPE_CORE, value=_OBJECTIVE_TYPE_CORE),
			discord.SelectOption(label=_OBJECTIVE_TYPE_NODE, value=_OBJECTIVE_TYPE_NODE),
		]
		super().__init__(placeholder="Select objective type", options=options, min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		view.state.objective_type = self.values[0]
		view._build_items()
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _VortexRaritySelect(discord.ui.Select):
	def __init__(self):
		options = [discord.SelectOption(label=_vortex_rarity_display(r), value=r) for r in _VORTEX_RARITIES]
		super().__init__(placeholder="Select vortex rarity", options=options, min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		view.state.vortex_rarity = self.values[0]
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _CoreRaritySelect(discord.ui.Select):
	def __init__(self):
		options = [discord.SelectOption(label=_vortex_rarity_display(r), value=r) for r in _VORTEX_RARITIES]
		super().__init__(placeholder="Select core rarity", options=options, min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		view.state.vortex_rarity = self.values[0]
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _NodeTypeSelect(discord.ui.Select):
	def __init__(self):
		options = [discord.SelectOption(label=t, value=t) for t in _NODE_TYPES]
		super().__init__(placeholder="Select node type", options=options, min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		view.state.node_type = self.values[0]
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _NodeTierSelect(discord.ui.Select):
	def __init__(self):
		options = [discord.SelectOption(label=t, value=t) for t in _NODE_TIERS]
		super().__init__(placeholder="Select node tier", options=options, min_values=1, max_values=1)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		view.state.node_tier = self.values[0]
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _NotifyBeforeSelect(discord.ui.Select):
	def __init__(self):
		options = [
			discord.SelectOption(label=f"{m} minutes", value=str(m)) for m in _NOTIFY_BEFORE_MINUTES_OPTIONS
		]
		super().__init__(
			placeholder="Notify before pop (minutes)",
			options=options,
			min_values=1,
			max_values=1,
		)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		try:
			minutes = int(self.values[0])
		except (TypeError, ValueError):
			minutes = 0
		if minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return
		view.state.notify_before_minutes = minutes
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _WizardCancelButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


class _WizardBackButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Back", style=discord.ButtonStyle.secondary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		if view.step > 1:
			view.step -= 1
		view._build_items()
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


class _WizardSaveContinueButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Save and Continue", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		error = _validate_step(view)
		if error:
			await _send_ephemeral_notice(interaction, error)
			return

		view.step += 1
		view._build_items()
		await interaction.response.edit_message(embed=_build_wizard_embed(view), view=view)


def _validate_step(view: ObjectiveWizardView) -> Optional[str]:
	if view.step == 1:
		if view.state.objective_type not in (_OBJECTIVE_TYPE_VORTEX, _OBJECTIVE_TYPE_CORE, _OBJECTIVE_TYPE_NODE):
			return "Please select objective type first."
		return None

	if view.state.objective_type == _OBJECTIVE_TYPE_VORTEX:
		if view.step == 2 and view.state.vortex_rarity not in _VORTEX_RARITIES:
			return "Please select vortex rarity first."
		if view.step == 3 and not view.state.pop_time_utc:
			return "Please set pop time first."
		if view.step == 4 and not view.state.map_name:
			return "Please set objective map first."
		if view.step == 5 and view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	if view.state.objective_type == _OBJECTIVE_TYPE_CORE:
		if view.step == 2 and view.state.vortex_rarity not in _VORTEX_RARITIES:
			return "Please select core rarity first."
		if view.step == 3 and not view.state.pop_time_utc:
			return "Please set pop time first."
		if view.step == 4 and not view.state.map_name:
			return "Please set objective map first."
		if view.step == 5 and view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	if view.state.objective_type == _OBJECTIVE_TYPE_NODE:
		if view.step == 2 and view.state.node_type not in _NODE_TYPES:
			return "Please select node type first."
		if view.step == 3 and view.state.node_tier not in _NODE_TIERS:
			return "Please select node tier first."
		if view.step == 4 and not view.state.pop_time_utc:
			return "Please set pop time first."
		if view.step == 5 and not view.state.map_name:
			return "Please set objective map first."
		if view.step == 6 and view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	return "Please select objective type first."


class _SetPopTimeButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set pop time", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		await interaction.response.send_modal(_PopTimeModal(view))


class _PopTimeModal(discord.ui.Modal, title="Set pop time (UTC)"):
	time_input = discord.ui.TextInput(
		label="Time (HH:MM)",
		placeholder="e.g. 17:34",
		required=True,
		max_length=5,
	)

	def __init__(self, parent_view: ObjectiveWizardView):
		super().__init__()
		self._parent_view = parent_view
		if parent_view.state.pop_time_utc:
			self.time_input.default = parent_view.state.pop_time_utc

	async def on_submit(self, interaction: discord.Interaction) -> None:
		raw = str(self.time_input).strip()
		parsed = _parse_utc_hhmm(raw)
		if parsed is None:
			await interaction.response.send_message(
				"Invalid time format. Use HH:MM (00:00-23:59).",
				ephemeral=True,
			)
			return

		hhmm, pop_at_ts = parsed
		self._parent_view.state.pop_time_utc = hhmm
		self._parent_view.state.pop_at_ts = pop_at_ts
		self._parent_view._build_items()
		await interaction.response.edit_message(embed=_build_wizard_embed(self._parent_view), view=self._parent_view)


_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _parse_utc_hhmm(raw_value: str) -> Optional[tuple[str, int]]:
	match = _HHMM_RE.match((raw_value or "").strip())
	if not match:
		return None

	try:
		hour = int(match.group(1))
		minute = int(match.group(2))
	except ValueError:
		return None

	if hour < 0 or hour > 23 or minute < 0 or minute > 59:
		return None

	now = datetime.now(timezone.utc)
	target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
	if target <= now:
		target = target + timedelta(days=1)
	hhmm = f"{hour:02d}:{minute:02d}"
	return hhmm, int(target.timestamp())


class _SetMapButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Set objective map", style=discord.ButtonStyle.primary)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return

		await interaction.response.send_modal(_MapModal(view))


class _MapModal(discord.ui.Modal, title="Set objective map"):
	map_input = discord.ui.TextInput(
		label="Map name",
		placeholder="e.g. Morgana's Rest",
		required=True,
		max_length=100,
	)

	def __init__(self, parent_view: ObjectiveWizardView):
		super().__init__()
		self._parent_view = parent_view
		if parent_view.state.map_name:
			self.map_input.default = parent_view.state.map_name

	async def on_submit(self, interaction: discord.Interaction) -> None:
		value = str(self.map_input).strip()
		self._parent_view.state.map_name = value
		self._parent_view._build_items()
		await interaction.response.edit_message(embed=_build_wizard_embed(self._parent_view), view=self._parent_view)



def _build_notify_role_name(obj: dict) -> str:
	obj_type = (obj.get("type") or "").strip() or "Objective"
	pop_time_utc = (obj.get("pop_time_utc") or "").strip() or "??:??"
	if obj_type in (_OBJECTIVE_TYPE_VORTEX, _OBJECTIVE_TYPE_CORE):
		rarity = (obj.get("rarity") or "").strip() or "?"
		return f"{obj_type}-{rarity}-{pop_time_utc}"
	if obj_type == _OBJECTIVE_TYPE_NODE:
		node_type = (obj.get("node_type") or "Node").strip() or "Node"
		tier = (obj.get("tier") or "").strip() or "?"
		return f"{node_type}-{tier}-{pop_time_utc}"
	return f"{obj_type}-{pop_time_utc}"


async def _ensure_notify_role(guild: discord.Guild, objective: dict) -> Optional[int]:
	role_name = _build_notify_role_name(objective)
	for role in guild.roles:
		if role.name == role_name:
			if not role.mentionable:
				try:
					await role.edit(mentionable=True, reason="Objective notification role")
				except (discord.Forbidden, discord.HTTPException):
					pass
			return int(role.id)

	try:
		role = await guild.create_role(
			name=role_name,
			mentionable=True,
			reason="Objective notification role",
		)
		return int(role.id)
	except (discord.Forbidden, discord.HTTPException):
		return None


class _WizardConfirmButton(discord.ui.Button):
	def __init__(self):
		super().__init__(label="Confirm and post objective", style=discord.ButtonStyle.success)

	async def callback(self, interaction: discord.Interaction) -> None:
		view = self.view
		if not isinstance(view, ObjectiveWizardView):
			return
		if interaction.user.id != view.user_id:
			return
		if interaction.guild is None:
			await _send_ephemeral_notice(interaction, "This can only be used inside a server.")
			return

		error = _validate_final(view)
		if error:
			await _send_ephemeral_notice(interaction, error)
			return

		objective = _build_objective_payload(view, interaction.user)
		objective["id"] = f"{interaction.guild.id}-{interaction.id}-{int(datetime.now(timezone.utc).timestamp())}"

		role_warning: Optional[str] = None
		role_id = await _ensure_notify_role(interaction.guild, objective)
		if role_id:
			objective["notify_role_id"] = int(role_id)
		else:
			role_warning = "Objective posted, but I couldn't create the notification role (missing Manage Roles permission?)."

		channel_id, message_id = get_objectives_panel_message(interaction.guild.id)
		if channel_id and message_id:
			try:
				panel_channel = interaction.guild.get_channel(channel_id)
				if panel_channel is None:
					panel_channel = await interaction.guild.fetch_channel(channel_id)

				if isinstance(panel_channel, discord.TextChannel):
					try:
						panel_message = await panel_channel.fetch_message(message_id)
						await panel_message.edit(
							embed=_build_panel_embed(interaction.guild),
							view=ObjectivesPanelView(),
						)
					except discord.NotFound:
						pass

					posted = await panel_channel.send(embed=_build_objective_embed(objective), view=ObjectiveMessageView())
					objective["channel_id"] = int(panel_channel.id)
					objective["message_id"] = int(posted.id)
					add_objective(interaction.guild.id, objective)

					try:
						panel_message = await panel_channel.fetch_message(message_id)
						await panel_message.edit(embed=_build_panel_embed(interaction.guild), view=ObjectivesPanelView())
					except (discord.NotFound, discord.Forbidden, discord.HTTPException):
						pass
			except (discord.Forbidden, discord.HTTPException):
				pass

		await interaction.response.edit_message(content=role_warning or "Objective posted.", embed=None, view=None)


def _validate_final(view: ObjectiveWizardView) -> Optional[str]:
	if view.state.objective_type == _OBJECTIVE_TYPE_VORTEX:
		if view.state.vortex_rarity not in _VORTEX_RARITIES:
			return "Please select vortex rarity."
		if not view.state.pop_time_utc or not view.state.pop_at_ts:
			return "Please set pop time."
		if not view.state.map_name:
			return "Please set objective map."
		if view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	if view.state.objective_type == _OBJECTIVE_TYPE_CORE:
		if view.state.vortex_rarity not in _VORTEX_RARITIES:
			return "Please select core rarity."
		if not view.state.pop_time_utc or not view.state.pop_at_ts:
			return "Please set pop time."
		if not view.state.map_name:
			return "Please set objective map."
		if view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	if view.state.objective_type == _OBJECTIVE_TYPE_NODE:
		if view.state.node_type not in _NODE_TYPES:
			return "Please select node type."
		if view.state.node_tier not in _NODE_TIERS:
			return "Please select node tier."
		if not view.state.pop_time_utc or not view.state.pop_at_ts:
			return "Please set pop time."
		if not view.state.map_name:
			return "Please set objective map."
		if view.state.notify_before_minutes not in _NOTIFY_BEFORE_MINUTES_OPTIONS:
			return "Please select when to notify before pop."
		return None

	return "Please select objective type."


def _build_objective_payload(view: ObjectiveWizardView, user: discord.abc.User) -> dict:
	payload: dict = {
		"type": view.state.objective_type,
		"map": view.state.map_name,
		"pop_time_utc": view.state.pop_time_utc,
		"pop_at_ts": view.state.pop_at_ts,
		"notify_before_minutes": int(view.state.notify_before_minutes)
		if view.state.notify_before_minutes is not None
		else None,
		"notify_at_ts": int(view.state.pop_at_ts - int(view.state.notify_before_minutes) * 60)
		if view.state.pop_at_ts and view.state.notify_before_minutes in _NOTIFY_BEFORE_MINUTES_OPTIONS
		else None,
		"created_at_ts": int(datetime.now(timezone.utc).timestamp()),
		"created_by": str(user),
		"created_by_id": int(user.id),
	}

	if view.state.objective_type in (_OBJECTIVE_TYPE_VORTEX, _OBJECTIVE_TYPE_CORE):
		payload["rarity"] = view.state.vortex_rarity
	elif view.state.objective_type == _OBJECTIVE_TYPE_NODE:
		payload["node_type"] = view.state.node_type
		payload["tier"] = view.state.node_tier

	return payload
