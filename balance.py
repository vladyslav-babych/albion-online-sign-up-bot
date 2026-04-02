import gspread
import time
from typing import Optional


COL_DISCORD_ID = 1
COL_ALBION_NICKNAME = 2
COL_SILVER = 4


def _find_first_matched_target(worksheet, col_index: int, target: str):
    values = worksheet.col_values(col_index)
    for row_index, value in enumerate(values, start=1):
        if value == target:
            return row_index
    return None


def _read_silver(worksheet, row_index: int) -> int:
    raw_silver = worksheet.cell(row_index, COL_SILVER).value
    if raw_silver is None or raw_silver == "":
        return 0
    return int(str(raw_silver).replace(' ', ''))


def _parse_silver_value(raw_silver: str) -> int:
    normalized = str(raw_silver).replace(" ", "").strip()
    if not normalized:
        return 0

    try:
        return int(normalized)
    except ValueError:
        return 0


def find_player_by_discord_id(rows: list, discord_id: int) -> Optional[tuple[int, str, int]]:
    discord_id_str = str(discord_id).strip()
    for row_index, row in enumerate(rows, start=1):
        if not row or not row[0].strip().isdigit():
            continue
        if row[0].strip() == discord_id_str:
            nickname = row[1].strip() if len(row) >= 2 else ""
            raw_silver = row[3].strip() if len(row) >= 4 else ""
            return row_index, nickname, _parse_silver_value(raw_silver)
    return None


def update_member_balance_by_discord_id(
    worksheet,
    rows: list,
    discord_id: int,
    delta: int,
    clamp_min_zero: bool = False,
) -> Optional[tuple[str, int]]:
    target_result = find_player_by_discord_id(rows, discord_id)
    if target_result is None:
        return None

    target_row_index, target_nickname, current_silver = target_result
    updated_silver = current_silver + delta
    if clamp_min_zero:
        updated_silver = max(updated_silver, 0)

    worksheet.update_cell(target_row_index, COL_SILVER, str(updated_silver))
    return target_nickname, updated_silver


def _is_quota_error(error: Exception) -> bool:
    if not isinstance(error, gspread.exceptions.APIError):
        return False

    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return True

    return "429" in str(error) or "quota" in str(error).lower()


def _call_with_backoff(operation, attempts: int = 5, initial_delay_seconds: float = 1.0):
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if not _is_quota_error(error) or attempt == attempts - 1:
                raise

            time.sleep(initial_delay_seconds * (2 ** attempt))

    if last_error is not None:
        raise last_error


def add_balances_for_lootsplit_batch(worksheet, participants: list[str], amount: int) -> tuple[list[tuple[str, str]], list[str]]:
    rows = _call_with_backoff(lambda: worksheet.get_all_values())

    index_by_nickname: dict[str, tuple[int, str, int]] = {}
    for row_index, row in enumerate(rows, start=1):
        if len(row) < COL_ALBION_NICKNAME:
            continue

        nickname = row[COL_ALBION_NICKNAME - 1].strip()
        if not nickname or nickname in index_by_nickname:
            continue

        discord_id = row[COL_DISCORD_ID - 1].strip() if len(row) >= COL_DISCORD_ID else ""
        if not discord_id.isdigit():
            continue

        raw_silver = row[COL_SILVER - 1].strip() if len(row) >= COL_SILVER else ""
        current_silver = _parse_silver_value(raw_silver)
        index_by_nickname[nickname] = (row_index, discord_id, current_silver)

    missing_participants: list[str] = []
    credited: list[tuple[str, str]] = []
    updated_silver_by_row: dict[int, int] = {}

    for participant_name in participants:
        match = index_by_nickname.get(participant_name)
        if match is None:
            if participant_name not in missing_participants:
                missing_participants.append(participant_name)
            continue

        row_index, discord_id, base_silver = match
        current_silver = updated_silver_by_row.get(row_index, base_silver)
        updated_silver = current_silver + amount
        updated_silver_by_row[row_index] = updated_silver
        credited.append((participant_name, discord_id))

    if updated_silver_by_row:
        updates = [
            {
                "range": f"D{row_index}:D{row_index}",
                "values": [[str(updated_silver)]],
            }
            for row_index, updated_silver in sorted(updated_silver_by_row.items())
        ]
        _call_with_backoff(lambda: worksheet.batch_update(updates, value_input_option="USER_ENTERED"))

    return credited, missing_participants


async def get_balance(context, worksheet, member=None):
    try:
        target = member or context.author
        row_index = _find_first_matched_target(worksheet, COL_DISCORD_ID, str(target.id))
        if row_index is None:
            await context.send("Balance not found.")
            return

        silver = _read_silver(worksheet, row_index)

        import discord

        embed = discord.Embed()
        embed.description = f"### {target.mention} balance:"
        embed.add_field(name="Balance", value=f"{silver:,} :coin:", inline=False)
        embed.add_field(name="Raw balance", value=str(silver), inline=False)
        await context.send(embed=embed)
    except Exception as e:
        await context.send(f"Error: {e}")