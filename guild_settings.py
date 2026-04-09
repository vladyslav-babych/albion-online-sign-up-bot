import json
from pathlib import Path
from typing import Optional


_GUILDS_FILE = Path("configs/guilds_config.json")


def _load_config() -> dict[str, dict]:
    if not _GUILDS_FILE.exists():
        return {}

    try:
        with _GUILDS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[str(key)] = {"guild_name": value, "member_role_name": "Member"}
        elif isinstance(value, dict):
            result[str(key)] = value
    return result


def _save_config(config: dict) -> None:
    with _GUILDS_FILE.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=True, indent=2)


def set_target_guild(
    discord_server_id: int,
    target_guild_name: str,
    member_role_name: str = "Member",
    caller_role_name: str = "Caller",
    economy_manager_role_name: str = "Economy Manager",
    leave_action: Optional[str] = None,
) -> None:
    config = _load_config()
    server_key = str(discord_server_id)
    existing_entry = config.get(server_key)
    base_entry = existing_entry.copy() if isinstance(existing_entry, dict) else {}
    base_entry["guild_name"] = target_guild_name.strip()
    base_entry["member_role_name"] = member_role_name.strip() or "Member"
    base_entry["caller_role_name"] = caller_role_name.strip() or "Caller"
    base_entry["economy_manager_role_name"] = economy_manager_role_name.strip() or "Economy Manager"
    normalized_leave_action = (leave_action or "").strip().lower()
    if normalized_leave_action:
        base_entry["leave_action"] = normalized_leave_action if normalized_leave_action in {"kick", "remove_roles", "none"} else "remove_roles"
    else:
        existing_leave_action = (base_entry.get("leave_action") or "").strip().lower()
        base_entry["leave_action"] = existing_leave_action if existing_leave_action in {"kick", "remove_roles", "none"} else "remove_roles"
    config[server_key] = base_entry
    _save_config(config)


def get_leave_action(discord_server_id: int) -> str:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not entry:
        return "remove_roles"
    value = (entry.get("leave_action") or "").strip().lower()
    return value if value in {"kick", "remove_roles", "none"} else "remove_roles"


def get_target_guild(discord_server_id: int) -> Optional[str]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not entry:
        return None
    return entry.get("guild_name", "").strip() or None


def get_member_role(discord_server_id: int) -> str:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not entry:
        return "Member"
    return entry.get("member_role_name", "Member") or "Member"


def get_caller_roles(discord_server_id: int) -> list[str]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not entry:
        return ["Caller"]
    raw = (entry.get("caller_role_name", "") or "").strip()
    if not raw:
        return ["Caller"]
    return [r.strip() for r in raw.split(",") if r.strip()]


def get_economy_manager_roles(discord_server_id: int) -> list[str]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not entry:
        return ["Economy Manager"]
    raw = (entry.get("economy_manager_role_name", "") or "").strip()
    if not raw:
        return ["Economy Manager"]
    return [r.strip() for r in raw.split(",") if r.strip()]


def set_bot_configuration_message(discord_server_id: int, channel_id: int, message_id: int) -> None:
    config = _load_config()
    server_key = str(discord_server_id)
    entry = config.get(server_key)
    if not isinstance(entry, dict):
        return

    entry["bot_config_channel_id"] = str(channel_id)
    entry["bot_config_message_id"] = str(message_id)
    config[server_key] = entry
    _save_config(config)


def get_bot_configuration_message(discord_server_id: int) -> tuple[Optional[int], Optional[int]]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return None, None

    raw_channel_id = entry.get("bot_config_channel_id")
    raw_message_id = entry.get("bot_config_message_id")
    try:
        channel_id = int(raw_channel_id) if raw_channel_id is not None else None
        message_id = int(raw_message_id) if raw_message_id is not None else None
    except (TypeError, ValueError):
        return None, None

    return channel_id, message_id


def set_bot_updates_channel(discord_server_id: int, channel_id: int) -> None:
    config = _load_config()
    server_key = str(discord_server_id)
    entry = config.get(server_key)
    base_entry = entry.copy() if isinstance(entry, dict) else {}
    base_entry["bot_updates_channel_id"] = str(channel_id)
    config[server_key] = base_entry
    _save_config(config)


def get_bot_updates_channel(discord_server_id: int) -> Optional[int]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return None

    raw_channel_id = entry.get("bot_updates_channel_id")
    try:
        return int(raw_channel_id) if raw_channel_id is not None else None
    except (TypeError, ValueError):
        return None


def get_all_bot_updates_channels() -> dict[int, int]:
    config = _load_config()
    result: dict[int, int] = {}

    for server_id, entry in config.items():
        if not isinstance(entry, dict):
            continue

        raw_channel_id = entry.get("bot_updates_channel_id")
        try:
            parsed_server_id = int(server_id)
            parsed_channel_id = int(raw_channel_id)
        except (TypeError, ValueError):
            continue

        result[parsed_server_id] = parsed_channel_id

    return result


def set_utc_timer_channel(discord_server_id: int, channel_id: int) -> None:
    config = _load_config()
    server_key = str(discord_server_id)
    entry = config.get(server_key)
    base_entry = entry.copy() if isinstance(entry, dict) else {}
    base_entry["utc_timer_channel_id"] = str(channel_id)
    config[server_key] = base_entry
    _save_config(config)


def get_utc_timer_channel(discord_server_id: int) -> Optional[int]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return None

    raw_channel_id = entry.get("utc_timer_channel_id")
    try:
        return int(raw_channel_id) if raw_channel_id is not None else None
    except (TypeError, ValueError):
        return None


def clear_utc_timer_channel(discord_server_id: int) -> None:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return

    if "utc_timer_channel_id" not in entry:
        return

    entry.pop("utc_timer_channel_id", None)
    config[str(discord_server_id)] = entry
    _save_config(config)


def get_all_utc_timer_channels() -> dict[int, int]:
    config = _load_config()
    result: dict[int, int] = {}

    for server_id, entry in config.items():
        if not isinstance(entry, dict):
            continue

        raw_channel_id = entry.get("utc_timer_channel_id")
        try:
            parsed_server_id = int(server_id)
            parsed_channel_id = int(raw_channel_id)
        except (TypeError, ValueError):
            continue

        result[parsed_server_id] = parsed_channel_id

    return result


def set_utc_timer_guild_name(discord_server_id: int, guild_name: str) -> None:
    config = _load_config()
    server_key = str(discord_server_id)
    entry = config.get(server_key)
    base_entry = entry.copy() if isinstance(entry, dict) else {}
    base_entry["utc_timer_guild_name"] = guild_name.strip()
    config[server_key] = base_entry
    _save_config(config)


def get_utc_timer_guild_name(discord_server_id: int) -> Optional[str]:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return None

    value = (entry.get("utc_timer_guild_name") or "").strip()
    return value or None


def clear_utc_timer_guild_name(discord_server_id: int) -> None:
    config = _load_config()
    entry = config.get(str(discord_server_id))
    if not isinstance(entry, dict):
        return

    if "utc_timer_guild_name" not in entry:
        return

    entry.pop("utc_timer_guild_name", None)
    config[str(discord_server_id)] = entry
    _save_config(config)


def get_all_utc_timer_guild_names() -> dict[int, str]:
    config = _load_config()
    result: dict[int, str] = {}

    for server_id, entry in config.items():
        if not isinstance(entry, dict):
            continue

        raw_name = (entry.get("utc_timer_guild_name") or "").strip()
        if not raw_name:
            continue

        try:
            parsed_server_id = int(server_id)
        except (TypeError, ValueError):
            continue

        result[parsed_server_id] = raw_name

    return result


def get_all_configured_server_ids() -> list[int]:
    config = _load_config()
    result: list[int] = []
    for server_id in config.keys():
        try:
            parsed = int(server_id)
        except (TypeError, ValueError):
            continue
        result.append(parsed)
    return result


def get_server_id_by_target_guild(target_guild_name: str) -> Optional[str]:
    config = _load_config()
    normalized_target = target_guild_name.strip().lower()

    for server_id, entry in config.items():
        guild_name = entry.get("guild_name", "").strip().lower()
        if guild_name == normalized_target:
            return server_id

    return None


def remove_target_guild(discord_server_id: int) -> Optional[str]:
    config = _load_config()
    entry = config.pop(str(discord_server_id), None)

    if entry is None:
        return None

    _save_config(config)
    return entry.get("guild_name") if isinstance(entry, dict) else entry
