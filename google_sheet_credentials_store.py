import json
import re
from pathlib import Path
from typing import Tuple


_CREDENTIALS_DIR = Path("google_sheet_credentials")
_LINKS_FILE = _CREDENTIALS_DIR / "credentials_links.json"


def _ensure_credentials_dir() -> None:
    _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_guild_name(guild_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", guild_name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "guild"


def _load_links() -> dict:
    if not _LINKS_FILE.exists():
        return {}

    try:
        with _LINKS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _save_links(links: dict) -> None:
    with _LINKS_FILE.open("w", encoding="utf-8") as file:
        json.dump(links, file, ensure_ascii=True, indent=2)


def link_google_sheet_credentials(
    discord_server_id: int,
    guild_name: str,
    credentials_text: str,
    google_sheet_name: str = "",
    google_worksheet_name: str = "",
    lootsplit_history_worksheet_name: str = "",
    balance_history_worksheet_name: str = "",
) -> Tuple[bool, str]:
    try:
        parsed_credentials = json.loads(credentials_text)
    except json.JSONDecodeError:
        return False, "**FAILED.** Credentials text is not valid JSON."

    if not isinstance(parsed_credentials, dict):
        return False, "**FAILED.** Credentials JSON must be an object."

    required_keys = {"client_email", "private_key", "project_id"}
    missing_keys = [key for key in required_keys if key not in parsed_credentials]
    if missing_keys:
        return False, f"**FAILED.** Credentials JSON is missing required key(s): {', '.join(missing_keys)}."

    _ensure_credentials_dir()

    resolved_sheet_name = google_sheet_name.strip() or guild_name
    resolved_worksheet_name = google_worksheet_name.strip() or "Players"
    resolved_lootsplit_history_worksheet_name = lootsplit_history_worksheet_name.strip() or "Lootsplit History"
    resolved_balance_history_worksheet_name = balance_history_worksheet_name.strip() or "Balance History"

    sanitized_guild_name = _sanitize_guild_name(guild_name)
    credentials_file_name = f"{sanitized_guild_name}_credentials.json"
    credentials_file_path = _CREDENTIALS_DIR / credentials_file_name

    with credentials_file_path.open("w", encoding="utf-8") as file:
        json.dump(parsed_credentials, file, ensure_ascii=True, indent=2)

    links = _load_links()
    links[str(discord_server_id)] = {
        "guild_name": guild_name,
        "credentials_file": credentials_file_name,
        "google_sheet_name": resolved_sheet_name,
        "google_worksheet_name": resolved_worksheet_name,
        "lootsplit_history_worksheet_name": resolved_lootsplit_history_worksheet_name,
        "balance_history_worksheet_name": resolved_balance_history_worksheet_name,
    }
    _save_links(links)

    return (
        True,
        (
            f"**SUCCESS.** Google Sheet credentials were linked to this server. Saved file: **{credentials_file_name}**\n"
            f"Sheet: **{resolved_sheet_name}**\n"
            f"Worksheet: **{resolved_worksheet_name}**\n"
            f"Lootsplit Worksheet: **{resolved_lootsplit_history_worksheet_name}**\n"
            f"Balance History Worksheet: **{resolved_balance_history_worksheet_name}**"
        ),
    )


def remove_google_sheet_credentials(discord_server_id: int) -> None:
    links = _load_links()
    
    server_id_str = str(discord_server_id)
    if server_id_str not in links:
        return
    
    credentials_file_name = links[server_id_str].get("credentials_file")
    
    if credentials_file_name:
        credentials_file_path = _CREDENTIALS_DIR / credentials_file_name
        if credentials_file_path.exists():
            credentials_file_path.unlink()
    
    del links[server_id_str]
    _save_links(links)


def get_credentials_info(discord_server_id: int) -> dict:
    links = _load_links()
    server_id_str = str(discord_server_id)
    
    if server_id_str not in links:
        return {}
    
    link_info = links[server_id_str]
    credentials_file_name = link_info.get("credentials_file")
    
    if not credentials_file_name:
        return {}
    
    credentials_file_path = _CREDENTIALS_DIR / credentials_file_name
    
    if not credentials_file_path.exists():
        return {}
    
    return {
        "credentials_file": str(credentials_file_path),
        "google_sheet_name": link_info.get("google_sheet_name"),
        "google_worksheet_name": link_info.get("google_worksheet_name"),
        "lootsplit_history_worksheet_name": link_info.get("lootsplit_history_worksheet_name", "Lootsplit History"),
        "balance_history_worksheet_name": link_info.get("balance_history_worksheet_name", "Balance History"),
    }


def update_credentials_link_field(discord_server_id: int, field_name: str, new_value: str) -> Tuple[bool, str]:
    links = _load_links()
    server_id_str = str(discord_server_id)
    link_info = links.get(server_id_str)

    if not isinstance(link_info, dict):
        return False, "Google Sheet is not linked yet. Run **/bot-link-google-sheet** first."

    allowed_fields = {
        "credentials_file",
        "google_sheet_name",
        "google_worksheet_name",
        "lootsplit_history_worksheet_name",
        "balance_history_worksheet_name",
    }
    if field_name not in allowed_fields:
        return False, "Unsupported configuration field."

    clean_value = new_value.strip()
    if not clean_value:
        return False, "Value cannot be empty."

    if field_name == "credentials_file":
        credentials_file_path = _CREDENTIALS_DIR / clean_value
        if not credentials_file_path.exists():
            return False, f"Credentials file **{clean_value}** was not found in `google_sheet_credentials/`."

    link_info[field_name] = clean_value
    links[server_id_str] = link_info
    _save_links(links)
    return True, "Configuration updated."
