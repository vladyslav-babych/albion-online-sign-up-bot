import globals
import gspread
import time
from typing import Optional


COL_DISCORD_ID = 1
COL_ALBION_NICKNAME = 2
COL_SILVER = 3


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
            raw_silver = row[2].strip() if len(row) >= 3 else ""
            return row_index, nickname, _parse_silver_value(raw_silver)
    return None


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
                "range": f"C{row_index}:C{row_index}",
                "values": [[str(updated_silver)]],
            }
            for row_index, updated_silver in sorted(updated_silver_by_row.items())
        ]
        _call_with_backoff(lambda: worksheet.batch_update(updates, value_input_option="USER_ENTERED"))

    return credited, missing_participants


def add_balance_for_lootsplit(worksheet, nickname: str, amount: int) -> tuple[str, int]:
    row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
    if row_index is None:
        raise ValueError(f"Character **{nickname}** not found.")

    current_silver = _read_silver(worksheet, row_index)
    updated_silver = current_silver + amount
    worksheet.update_cell(row_index, COL_SILVER, str(updated_silver))

    discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
    return str(discord_id), updated_silver


async def get_balance(context, worksheet, nickname: str = None):
    try:
        if nickname is None:
            row_index = _find_first_matched_target(worksheet, COL_DISCORD_ID, str(context.author.id))
            mention = context.author.mention
        else:
            row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
            discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
            mention = f"<@{discord_id}>"
        if row_index is None:
            await context.send("Balance not found.")
            return

        silver = _read_silver(worksheet, row_index)
        await context.send(f"{mention} balance: **{silver}** :coin:")
    except Exception as e:
        await context.send(f"Error: {e}")


async def remove_balance(context, worksheet, nickname: str, amount: int):
    if not await globals.is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return
    try:
        amount_int = int(amount)
    except ValueError:
        await context.reply("Amount must be an integer.")
        return

    if amount_int < 0:
        await context.reply("Amount must be >= 0.")
        return
    try:
        row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
        if row_index is None:
            await context.send(f"Character **{nickname}** not found.")
            return

        current_silver = _read_silver(worksheet, row_index)
        updated_silver = max(current_silver - amount_int, 0)     
        worksheet.update_cell(row_index, COL_SILVER, str(updated_silver))
        
        discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
        mention = f"<@{discord_id}>"
        await context.send(f"{mention} balance: **{updated_silver}** :coin:")

    except Exception as e:
        await context.send(f"Error: {e}")


async def add_balance(context, worksheet, nickname: str, amount: int):
    if not await globals.is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return
    try:
        amount_int = int(amount)
    except ValueError:
        await context.reply("Amount must be an integer.")
        return

    if amount_int < 0:
        await context.reply("Amount must be >= 0.")
        return

    try:
        discord_id, updated_silver = add_balance_for_lootsplit(worksheet, nickname, amount_int)
        mention = f"<@{discord_id}>"
        await context.send(f"{mention} balance: **{updated_silver}** :coin:")

    except Exception as e:
        await context.send(f"Error: {e}")