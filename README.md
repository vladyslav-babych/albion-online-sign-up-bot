# KINGSBLOOD_BOT

Discord bot for Albion guild operations: registration, party comp management, lootsplit payouts, and Google Sheets-based accounting/history.

## Current architecture

- `main.py` contains only bot bootstrap + command routing.
- `command_handlers.py` contains all command logic.
- `modals.py` contains setup/link modals and persistent configuration message handling.
- `guild_settings.py` stores per-server bot config (`guild_name`, `caller_role_name`, `economy_manager_role_name`, `member_role_name`, config-message ids).
- `google_sheet_credentials_store.py` stores Google Sheet link metadata per server.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set bot token in environment (used by code as `DISCORD_TOKEN`).
4. Run:

```bash
python main.py
```

5. In Discord (server admin):
	 - Run `/bot-setup`
	 - Run `/bot-link-google-sheet`

## Security warning

- Service account credentials you provide via `/bot-link-google-sheet` are stored as local JSON files in `google_sheet_credentials/`.
- The bot owner/operator has access to these credential files.
- Set up and use this bot at your own risk.
- Use a dedicated, least-privilege Google service account only for this bot.

## Commands

### Prefix commands

- `!create-comp <comp_message_id> <source_channel_id>`
- `!get-participants <battle_ids>`
- `!bal [nickname]`
- `/bot-remove`
- `!clear`

### Slash commands

- `/bot-setup`
- `/bot-link-google-sheet`
- `/tickets-setup`
- `/update-config`
- `/register`
- `/lootsplit`
- `/bal-add`
- `/bal-remove`

## Permissions model

- Admin-only:
	- `/bot-setup`, `/bot-link-google-sheet`, `/tickets-setup`, `/update-config`, `/bot-remove`, `!clear`
- Economy operations (`/lootsplit`, `/bal-add`, `/bal-remove`):
	- allowed for Admins OR members with configured Economy Manager role(s)
- Comp officer actions (`!create-comp`, forced sign-up/sign-out in party threads):
	- allowed for Admins OR members with configured Caller role(s)
- `/register`, `!bal`, and normal thread self sign-up/sign-out are available without admin requirement.

## Bot setup and configuration

### `/bot-setup`

Configures per-server values:

- Guild name
- Caller role name(s) (default: `Caller`, supports CSV like `Caller, War Master`)
- Economy Manager role name(s) (default: `Economy Manager`, supports CSV like `Economy Manager, Banker`)
- Member role name (default: `Member`)

After setup, bot posts/updates a persistent **Bot configuration** message in the channel.

### `/bot-link-google-sheet`

Links service account JSON and sheet mapping:

- Credentials JSON (full service account JSON text)
- Google Sheet name (default: guild name)
- Players worksheet name (default: `Players`)
- Lootsplit History worksheet name (default: `Lootsplit History`)
- Balance History worksheet name (default: `Balance History`)

After linking, the same persistent configuration message is updated.

### `/update-config`

Interactive update flow in chat:

1. Bot posts numbered menu `(1)`..`(9)`
2. Admin replies with number
3. Bot asks for new value
4. Bot updates related JSON store and refreshes persistent configuration message

Supported fields:

1. Guild name
2. Caller role(s)
3. Economy Manager role(s)
4. Member role
5. Credentials file
6. Google Sheet name
7. Players Worksheet name
8. Lootsplit History Worksheet name
9. Balance History Worksheet name
10. Exit

Safety checks:

- Guild name update is blocked if already used by another server.
- Credentials file update requires the file to exist in `google_sheet_credentials/`.

## Ticket system

### `/tickets-setup`

Admin command used to configure guild application ticket panels.

Main setup entry has 2 buttons:

- `Create Panel`
- `Manage Panels`

### Create Panel flow

Panel creation uses 6 steps:

1. Set panel name
2. Select management team role(s)
3. Select ticket category
4. Select panel destination channel
5. Set panel message and ticket opening message
6. Review summary and finish

The created panel contains an `Open Ticket` button.

The message step opens a modal where admin can customize:

- the panel embed message shown before opening a ticket
- the opening message shown inside newly created tickets

### Ticket behavior

- Clicking `Open Ticket` creates a new text channel under the selected category.
- Ticket names are generated as `ticket-0001`, `ticket-0002`, and so on.
- Only the applicant and selected management team can view the ticket.
- The ticket contains a `Close Ticket` button.
- When management team closes the ticket:
	- channel is renamed to `closed-0001`
	- applicant loses send permission

### Manage Panels

Manage Panels lets admin:

- view configured panels
- send a selected panel again to its configured destination channel
- delete a selected panel

## Registration and balances

### `/register <character_name>`

- Validates user against configured guild (Albion API check).
- Adds row to Players worksheet with:
	- Discord ID
	- Albion nickname
	- Silver (starts at `0`)
- Updates Discord nickname to Albion nickname.
- Adds configured Member role.

### `!bal [nickname]`

- Reads Silver from Players worksheet by Discord ID (self) or specified nickname.

### `/bal-add` and `/bal-remove`

- Work by Discord member mention.
- Validate amount as integer `>= 0`.
- Update Silver in Players worksheet.
- Write one row to Balance History worksheet:
	- Date, Reason, Officer, Nickname, Amount
- Defaults:
	- `/bal-add` reason: `Manual`
	- `/bal-remove` reason: `Payout`

## Lootsplit flow

### `/lootsplit`

Inputs:

- `battle_ids` (CSV)
- `officer`
- `content_name`
- `caller`
- `participants` (CSV)
- `lootsplit_amount`

Behavior:

- Credits balances in batch for found participants.
- Appends Lootsplit History rows in batch.
- Appends Balance History rows (reason: `Lootsplit`) for credited players.
- Reports missing and failed participants separately.

Google Sheets operations use retry-with-backoff for quota (`429`) errors.

## Party comp thread behavior

In `Party ... thread` threads:

- `1` → sign up to role `1`
- `-` → sign out self
- `-1` → force sign out role `1` (caller/admin only)
- `@User 1` → force sign up mentioned user to role `1` (caller/admin only)

## Data files

- `configs/guilds_config.json`:
	- guild mapping + role config + persistent config message references
- `google_sheet_credentials/credentials_links.json`:
	- per-server sheet and worksheet mapping
- `google_sheet_credentials/*_credentials.json`:
	- stored service account credentials

## Notes

- Enable **Developer Mode** in Discord to copy message/channel IDs for `!create-comp`.
- If you rename worksheet tabs in Google Sheets, update mapping via `/update-config` or relink with `/bot-link-google-sheet`.