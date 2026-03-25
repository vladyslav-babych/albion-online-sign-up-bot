from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
import google_sheet_credentials_store
import logging
import time


GOOGLE_SHEET_SCOPES = 'https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/drive'
WORKSHEET_TYPE_PLAYERS = "players"
WORKSHEET_TYPE_LOOTSPLIT_HISTORY = "lootsplit_history"
WORKSHEET_TYPE_BALANCE_HISTORY = "balance_history"

LOOTSPLIT_HISTORY_HEADERS = [
	"Battleboard ID",
	"Date",
	"Officer",
	"Content name",
	"Caller",
	"Participant",
	"Lootsplit",
]

BALANCE_HISTORY_HEADERS = [
	"Date",
	"Reason",
	"Officer",
	"Nickname",
	"Amount",
]


def _parse_scopes(raw_scopes: Optional[str]) -> list[str]:
	return [scope.strip() for scope in raw_scopes.split(",") if scope.strip()]


def _resolve_worksheet_name(creds_info: dict, worksheet_type: str) -> str:
    if worksheet_type == WORKSHEET_TYPE_LOOTSPLIT_HISTORY:
        return creds_info.get("lootsplit_history_worksheet_name", "Lootsplit History")

    if worksheet_type == WORKSHEET_TYPE_BALANCE_HISTORY:
        return creds_info.get("balance_history_worksheet_name", "Balance History")

    return creds_info.get("google_worksheet_name")


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


def get_worksheet(discord_server_id: Optional[int] = None, worksheet_type: str = WORKSHEET_TYPE_PLAYERS):
	credentials_file = None
	sheet_name = None
	worksheet_name = None
	
	if discord_server_id is not None:
		creds_info = google_sheet_credentials_store.get_credentials_info(discord_server_id)
		if creds_info:
			credentials_file = creds_info.get("credentials_file")
			sheet_name = creds_info.get("google_sheet_name")
			worksheet_name = _resolve_worksheet_name(creds_info, worksheet_type)

	scopes = _parse_scopes(GOOGLE_SHEET_SCOPES)
	creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
	client = gspread.authorize(creds)

	return client.open(sheet_name).worksheet(worksheet_name)


def get_lootsplit_history_headers() -> list[str]:
    return LOOTSPLIT_HISTORY_HEADERS.copy()


def add_lootsplit_history_rows(worksheet, rows: list[list[str]]):
	if not rows:
		return

	string_rows = [[str(cell) for cell in row] for row in rows]
	_call_with_backoff(lambda: worksheet.append_rows(string_rows, value_input_option="RAW"))


def ensure_lootsplit_history_headers(worksheet):
	headers = get_lootsplit_history_headers()
	first_row = _call_with_backoff(lambda: worksheet.row_values(1))
	first_row_padded = first_row[:len(headers)] + [""] * max(0, len(headers) - len(first_row))

	if first_row_padded != headers:
		_call_with_backoff(lambda: worksheet.update("A1:G1", [headers]))


def ensure_balance_history_headers(worksheet):
	first_row = _call_with_backoff(lambda: worksheet.row_values(1))
	first_row_padded = first_row[:len(BALANCE_HISTORY_HEADERS)] + [""] * max(0, len(BALANCE_HISTORY_HEADERS) - len(first_row))

	if first_row_padded != BALANCE_HISTORY_HEADERS:
		_call_with_backoff(lambda: worksheet.update("A1:E1", [BALANCE_HISTORY_HEADERS]))


def add_balance_history_row(worksheet, date_utc: str, reason: str, officer: str, nickname: str, amount: int):
	row_values = [date_utc, reason, officer, nickname, str(amount)]
	_call_with_backoff(lambda: worksheet.append_row(row_values, value_input_option="RAW"))


def add_balance_history_rows(worksheet, rows: list):
	if not rows:
		return
	string_rows = [[str(cell) for cell in row] for row in rows]
	_call_with_backoff(lambda: worksheet.append_rows(string_rows, value_input_option="RAW"))


def registration_exists(worksheet, discord_id, albion_nickname):
	discord_id_str = str(discord_id).strip()
	albion_nickname_normalized = albion_nickname.strip().lower()

	for row in worksheet.get_all_values():
		if len(row) < 2:
			continue

		current_discord_id = row[0].strip()
		current_albion_nickname = row[1].strip().lower()

		if current_discord_id == discord_id_str:
			return True, "discord_id"

		if current_albion_nickname == albion_nickname_normalized:
			return True, "albion_nickname"

	return False, None


def find_registration_row_by_discord_id(worksheet, discord_id) -> Optional[tuple[int, list[str]]]:
	discord_id_str = str(discord_id).strip()
	if not discord_id_str:
		return None

	rows = _call_with_backoff(lambda: worksheet.get_all_values())
	for index, row in enumerate(rows, start=1):
		if not row:
			continue
		current_discord_id = (row[0] if len(row) >= 1 else "").strip()
		if current_discord_id == discord_id_str:
			return index, row

	return None


def reactivate_registration(worksheet, discord_id, albion_nickname: str) -> bool:
	found = find_registration_row_by_discord_id(worksheet, discord_id)
	if not found:
		return False

	row_index, row = found
	current_flag = (row[2] if len(row) >= 3 else "").strip().upper()
	if current_flag == "YES":
		return False

	nickname_value = (albion_nickname or "").strip()
	if not nickname_value:
		return False

	if len(row) >= 4:
		_call_with_backoff(lambda: worksheet.update(
			f"B{row_index}:C{row_index}",
			[[nickname_value, "YES"]],
			value_input_option="RAW",
		))
		return True

	silver_value = "0"
	if len(row) == 3:
		third_value = (row[2] or "").strip()
		if third_value and third_value.upper() not in {"YES", "NO"}:
			silver_value = third_value

	new_row_values = [str(discord_id).strip(), nickname_value, "YES", str(silver_value).strip() or "0"]
	_call_with_backoff(lambda: worksheet.update(
		f"A{row_index}:D{row_index}",
		[new_row_values],
		value_input_option="RAW",
	))
	return True


def add_user_to_worksheet(worksheet, discord_id, albion_nickname, silver=0):
	new_row_values = [
		str(discord_id),
		albion_nickname,
		"YES",
		str(silver),
	]

	rows = worksheet.get_all_values()
	first_empty_row = None

	for index, row in enumerate(rows, start=1):
		row_values = row[:4] + [""] * max(0, 4 - len(row))
		if all(not value.strip() for value in row_values):
			first_empty_row = index
			break

	if first_empty_row is None:
		first_empty_row = len(rows) + 1

	worksheet.update(f"A{first_empty_row}:D{first_empty_row}", [new_row_values])


def batch_update_in_guild_flags(worksheet, updates: list[tuple[int, str]]):
	if not updates:
		return
	requests = []
	for row_index, value in updates:
		try:
			row_index_int = int(row_index)
		except (TypeError, ValueError):
			continue
		if row_index_int <= 0:
			continue
		requests.append({
			"range": f"C{row_index_int}:C{row_index_int}",
			"values": [[str(value).strip()]],
		})
	if not requests:
		return
	_call_with_backoff(lambda: worksheet.batch_update(requests, value_input_option="RAW"))


def get_registered_nicknames(worksheet) -> list[str]:
    rows = worksheet.get_all_values()
    return [row[1].strip() for row in rows if len(row) >= 2 and row[1].strip()]


async def get_server_worksheet_or_notice(context):
    if context.guild is None:
        await context.send("This command can only be used inside a server.")
        return None

    try:
        return get_worksheet(context.guild.id)
    except gspread.exceptions.SpreadsheetNotFound:
        await context.send(
            "Google Sheet setup error: your **Google Sheet Name** does not match or this bot has no access to that sheet. "
            "Check **/bot-link-google-sheet** and share the sheet with the service account email."
        )
    except gspread.exceptions.WorksheetNotFound:
        await context.send(
            "Google Sheet setup error: your **Google Worksheet Name** does not match. "
            "Check **/bot-link-google-sheet** and verify the worksheet tab name."
        )
    except gspread.exceptions.APIError as error:
        await context.send(
            "Google API error while opening the sheet. Verify Google APIs are enabled and the credentials are valid."
        )
        logging.exception("Google API error while loading worksheet: %s", error)
    except Exception as error:
        await context.send(
			"Sheet configuration error: verify your Google Sheet, worksheet, and expected columns (Discord ID, Albion Nickname, Is In Guild, Silver)."
        )
        logging.exception("Unexpected worksheet loading error: %s", error)

    return None


async def get_server_lootsplit_history_worksheet_or_notice(context):
	if context.guild is None:
		await context.send("This command can only be used inside a server.")
		return None

	try:
		return get_worksheet(context.guild.id, worksheet_type=WORKSHEET_TYPE_LOOTSPLIT_HISTORY)
	except gspread.exceptions.SpreadsheetNotFound:
		await context.send(
			"Google Sheet setup error: your **Google Sheet Name** does not match or this bot has no access to that sheet. "
			"Check **/bot-link-google-sheet** and share the sheet with the service account email."
		)
	except gspread.exceptions.WorksheetNotFound:
		await context.send(
			"Google Sheet setup error: your **Lootsplit Worksheet Name** does not match. "
			"Check **/bot-link-google-sheet** and verify the lootsplit worksheet tab name."
		)
	except gspread.exceptions.APIError as error:
		await context.send(
			"Google API error while opening the sheet. Verify Google APIs are enabled and the credentials are valid."
		)
		logging.exception("Google API error while loading lootsplit worksheet: %s", error)
	except Exception as error:
		await context.send(
			"Sheet configuration error: verify your Google Sheet, lootsplit worksheet, and expected columns."
		)
		logging.exception("Unexpected lootsplit worksheet loading error: %s", error)

	return None


async def get_server_balance_history_worksheet_or_notice(context):
	if context.guild is None:
		await context.send("This command can only be used inside a server.")
		return None

	try:
		return get_worksheet(context.guild.id, worksheet_type=WORKSHEET_TYPE_BALANCE_HISTORY)
	except gspread.exceptions.SpreadsheetNotFound:
		await context.send(
			"Google Sheet setup error: your **Google Sheet Name** does not match or this bot has no access to that sheet. "
			"Check **/bot-link-google-sheet** and share the sheet with the service account email."
		)
	except gspread.exceptions.WorksheetNotFound:
		await context.send(
			"Google Sheet setup error: your **Balance History Worksheet Name** does not match. "
			"Check **/bot-link-google-sheet** and verify the balance history worksheet tab name."
		)
	except gspread.exceptions.APIError as error:
		await context.send(
			"Google API error while opening the sheet. Verify Google APIs are enabled and the credentials are valid."
		)
		logging.exception("Google API error while loading balance history worksheet: %s", error)
	except Exception as error:
		await context.send(
			"Sheet configuration error: verify your Google Sheet, balance history worksheet, and expected columns."
		)
		logging.exception("Unexpected balance history worksheet loading error: %s", error)

	return None