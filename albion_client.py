import requests
import guild_settings
from typing import List, Optional


BASE_URL = 'https://gameinfo-ams.albiononline.com/api/gameinfo'
SEARCH_ENDPOINT = '/search?q='
BATTLE_ENDPOINT = '/battles/'
PLAYER_ENDPOINT = '/players/'


def _get_search_url(query):
    return BASE_URL + SEARCH_ENDPOINT + query


def get_player_by_nickname(nickname):
    url = _get_search_url(nickname)
    response = requests.get(url).json()
    players = response.get('players', [])
    if not players:
        return None
    return players[0]


def find_player_id_by_exact_nickname(nickname: str) -> Optional[str]:
    """Find a player ID by exact nickname match (case-insensitive) using the search endpoint."""
    query = (nickname or "").strip()
    if not query:
        return None

    url = _get_search_url(query)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    players = data.get("players", [])
    if not isinstance(players, list):
        return None

    lowered = query.casefold()
    for item in players:
        if not isinstance(item, dict):
            continue
        name = (item.get("Name") or "").strip()
        if name and name.casefold() == lowered:
            pid = item.get("Id")
            return str(pid) if pid else None

    return None


def get_player_profile_by_id(player_id: str) -> Optional[dict]:
    """Fetch full player profile by ID from the Albion GameInfo API."""
    pid = (player_id or "").strip()
    if not pid:
        return None

    url = BASE_URL + PLAYER_ENDPOINT + pid
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def get_player_profile_by_exact_nickname(nickname: str) -> Optional[dict]:
    """Resolve a player by exact nickname, then fetch full profile (includes LifetimeStatistics)."""
    pid = find_player_id_by_exact_nickname(nickname)
    if not pid:
        return None
    return get_player_profile_by_id(pid)


def _get_battle_participants(battle_id: int) -> Optional[List[dict]]:
    url = BASE_URL + BATTLE_ENDPOINT + str(battle_id)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    players = data.get('players', {})
    return [p for p in players.values() if p.get('name')]


async def get_battle_participants(context, battle_ids: str):
    target_guild_name = guild_settings.get_target_guild(context.guild.id)
    if not target_guild_name:
        await context.send("This server is not configured yet. Ask an admin to run **/bot-setup** first.")
        return

    ids = [battle_id.strip() for battle_id in battle_ids.split(',') if battle_id.strip()]
    if not ids:
        await context.send("Please provide at least one battle ID.")
        return

    guild_members = set()
    failed_ids = []

    for battle_id in ids:
        try:
            battle_id = int(battle_id)
        except ValueError:
            failed_ids.append(battle_id)
            continue

        participants = _get_battle_participants(battle_id)
        if participants is None:
            failed_ids.append(str(battle_id))
            continue

        for p in participants:
            if p.get('guildName', '') == target_guild_name:
                guild_members.add(p['name'])

    if failed_ids:
        await context.send(f"Could not fetch battle(s): **{', '.join(failed_ids)}**. Check the IDs and try again.")

    if not guild_members:
        await context.send(f"No **{target_guild_name}** members found in the provided battle(s).")
        return

    sorted_members = sorted(guild_members)
    names_list = ','.join(sorted_members)
    battle_label = ', '.join(ids)
    await context.send(f"**{len(sorted_members)} {target_guild_name} member(s) in battle(s) {battle_label}:**\n{names_list}")
