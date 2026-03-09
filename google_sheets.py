import os
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials

def _parse_scopes(raw_scopes: Optional[str]) -> list[str]:
	return [scope.strip() for scope in raw_scopes.split(",") if scope.strip()]


def get_worksheet():
	credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
	sheet_name = os.getenv("GOOGLE_SHEET_NAME")
	worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME")

	scopes = _parse_scopes(os.getenv("GOOGLE_SHEET_SCOPES"))
	creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
	client = gspread.authorize(creds)

	return client.open(sheet_name).worksheet(worksheet_name)


def registration_exists(worksheet, discord_id, albion_nickname):
	discord_id_str = str(discord_id).strip()
	albion_nickname_normalized = albion_nickname.strip().lower()

	for row in worksheet.get_all_values():
		if len(row) < 3:
			continue

		current_discord_id = row[0].strip()
		current_albion_nickname = row[2].strip().lower()

		if current_discord_id == discord_id_str:
			return True, "discord_id"

		if current_albion_nickname == albion_nickname_normalized:
			return True, "albion_nickname"

	return False, None


def add_user_to_worksheet(worksheet, discord_id, albion_id, albion_nickname, silver=0):
	new_row_values = [
		str(discord_id),
		str(albion_id),
		albion_nickname,
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