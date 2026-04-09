# Realm Protector discord bot

Discord bot for Albion guild operations and management: registration, party comp management, lootsplit payouts, and Google Sheets-based accounting/history.

## Invitation setup:

1. Use the following link to invite bot to your server: https://discord.com/oauth2/authorize?client_id=1473795901079421152&permissions=7337378717101142&integration_type=0&scope=bot

2. In Discord (server admin):
	 - Run `/bot-setup` (required for most commands)
	 - Run `/bot-link-google-sheet` (optional, but required for some setups and commands)

## Local setup

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
	 - Run `/bot-setup` (required for most commands)
	 - Run `/bot-link-google-sheet` (optional, but required for some setups and commands)

## Security warning

- Service account credentials you provide via `/bot-link-google-sheet` and all setup configurations are stored as local JSON files.
- The bot owner/operator has access to the credentials and configuration files.
- Set up and use this bot at your own risk.
- Use a dedicated, least-privilege Google service account only for the Google Sheets link.

## Prefix commands

- `!create-comp <comp_message_id> <source_channel_id>`

## Slash commands

- `/bot-setup`
- `/bot-link-google-sheet`
- `/bot-remove`
- `/tickets-setup`
- `/role-reaction-setup`
- `/set-objective-panel`
- `/update-config`
- `/register`
- `/get-participants`
- `/lootsplit`
- `/bal`
- `/get-negative-siphon`
- `/bal-add`
- `/bal-remove`
- `/clear`
- `/add-utc-timer`

## Permissions model

- Admin-only:
	- `/bot-setup`, `/bot-link-google-sheet`, `/tickets-setup`, `/update-config`, `/bot-remove`, `/clear`, `/add-utc-timer`
- Economy operations (`/lootsplit`, `/get-negative-siphon`, `/bal-add`, `/bal-remove`):
	- Allowed for Admins OR members with configured Economy Manager role(s)
- Comp officer actions (`!create-comp`, forced sign-up/sign-out in party threads):
	- Allowed for Admins OR members with configured Caller role(s)
- `/register`, `/bal`, `/get-participants`, and normal thread self sign-up/sign-out are available without admin requirement.

## Bot setup and configuration

### `/bot-setup`

Configures per-server values:

- Guild name
- Caller role(s) selection
- Economy Manager role(s) selection
- Member role selection
- Bot updates channel selection
- Leave guild action (Kick from server / Remove all roles / Do nothing)

After setup, bot posts/updates a persistent **Bot configuration** message in the channel.

### `/bot-link-google-sheet`

Links service account JSON and sheet mapping:

- Credentials JSON (full service account JSON text)
- Google Sheet name (default: refers to guild name that was set up in `/bot-setup`)
- Players worksheet name (default: `Players`)
- Lootsplit History worksheet name (default: `Lootsplit History`)
- Balance History worksheet name (default: `Balance History`)

After linking, the same persistent configuration message is updated.  

Your linked Google Sheet is required to have 3 worksheets with the **EXACT** naming you provided in `/bot-link-google-sheet`:

- **Players** worksheet, column names **MUST** match those that are indicated in the example (values are for example):

| Discord ID | Albion Nickname | Is In Guild | Silver | Siphon |
|------------|-----------------|-------------|--------|--------|
| 1234567890 | Nickname | YES | 0 | 0 |  

- **Lootsplit History** worksheet, column names **MUST** match those that are indicated in the example (values are for example):

| Battleboard ID | Date | Officer | Content name | Caller | Participant | Lootsplit |
|----------------|------|---------|--------------|--------|-------------|-----------|
| 1234567890 | 03/24/26 17:44 UTC | Officer name | Terry defence | Caller name | Participant name | 2500000 |  

- **Balance History** worksheet, column names **MUST** match those that are indicated in the example (values are for example):

| Date | Reason | Officer | Nickname | Amount |
|------|--------|---------|----------|--------|
| 03/24/26 17:44 UTC | Payout | Officer name | Player name | -2500000 |

**Note:** If at least 1 letter in the column name will not match, logging and registration will not work.

- You can make a copy of the following Google Sheet: https://docs.google.com/spreadsheets/d/1N9YYq0tNboJsG0n9fvTngG0JfXxO2zwaKAKMPEWjBuc

### `/update-config`

Interactive update panel in chat:

1. Bot posts an interactive panel in chat
2. Admin selects the configuration that needs to be updated
3. Admin enters or selects a new value for the chosen configuration
4. After confirmation, bot updates the associated JSON file and updates the persistent configuration panel

Supported fields:

1. Guild name
2. Caller role(s)
3. Economy Manager role(s)
4. Member role
5. Leave guild action
6. Credentials file
7. Google Sheet name
8. Players Worksheet name
9. Lootsplit History Worksheet name
10. Balance History Worksheet name

Safety checks:

- Guild name update is blocked if already used by another server.
- Credentials file update requires the file to exist in `google_sheet_credentials/`.

## Guild membership tracking

The bot runs a background audit every **5 minutes** to detect players who left the configured Albion guild.

- If Google Sheets is linked, the bot uses the Players worksheet as the registration source of truth and updates **Is In Guild** from `YES` → `NO` when a player is detected outside the guild.
- The configured **Leave guild action** is then applied:
	- **Kick from server**
	- **Remove all roles** (all non-managed roles the bot is allowed to remove)
	- **Do nothing**

## Ticket system

### `/tickets-setup`

Admin command used to configure guild application ticket panels.

Main setup entry has 2 buttons:

- `Create Panel`
- `Manage Panels`

### Create Panel flow

Panel creation uses 7 steps:

1. Set panel name
2. Select management team role(s)
3. Select open ticket category
4. Select ticket archive channel
5. Select panel destination channel
6. Set panel message and ticket opening message
7. Review summary and finish

The created panel contains an `Open Ticket` button.

The message step opens a modal where admin can customize:

- The panel embed message shown before opening a ticket
- The opening message shown inside newly created tickets

### Ticket behavior

- Clicking `Open Ticket` opens a modal where the user must enter their **Albion character nickname**.
- The bot verifies the character exists and shows a confirmation panel with basic stats.
- If user confirms, the bot creates a new text channel under the selected category.
- Ticket names are generated as `open-character_nickname-0001`, `open-character_nickname-0002`, and so on.
- Only the applicant and selected management team can view the ticket.
- The ticket contains a `Close Ticket` button.
- When management team closes the ticket:
	- Bot sends an archive entry to the configured ticket archive channel (message content: character nickname)
	- Bot creates a thread under the archive message and forwards the ticket messages (including links and attachment URLs)
	- Bot deletes the ticket channel

### Manage Panels

Manage Panels lets admin:

- View configured panels
- Send a selected panel again to its configured destination channel
- Delete a selected panel

## Role reaction panels

### `/role-reaction-setup`

Admin command used to configure **role reaction panels**.

The setup message contains 2 buttons:

- `Create new panel`
- `Manage panels`

### Create new panel flow

Panel creation uses 5 steps:

1. Set panel name
2. Set panel message
3. Add emoji → role mappings (up to 6)
4. Select destination channel
5. Preview summary and confirm

When confirmed, the bot sends an embed to the chosen destination channel and adds the configured reactions.

### Role reaction behavior

- When a user reacts to a configured emoji, the bot adds the associated role.
- When a user removes the reaction, the bot removes the associated role.
- Only Unicode emojis are supported (you can also input a shortcode like `:gear:` during setup).

Required bot permissions:

- In the destination channel: **View Channel**, **Send Messages**, **Embed Links**, **Add Reactions**
- In the server: **Manage Roles** (and the bot role must be above the roles it needs to grant)

### Manage panels

Manage panels lets admin:

- Resend a selected panel to its configured destination channel (updates stored message reference)
- Delete a selected panel (also attempts to delete the last sent panel message)

## Objectives panel

### `/set-objective-panel`

Admin command that posts or updates a persistent **Objectives panel** in the current channel.

- Requires the server to be configured first via `/bot-setup`.
- If a panel already exists in another channel, the bot moves it by deleting the old message (or editing it with a “moved” notice if it cannot delete).

## UTC timer voice channel

### `/add-utc-timer`

Admin command that creates one voice channel per server whose name shows the current UTC time in `UTC HH:MM` format.

- The bot updates the channel name every 10 minutes. Discord rate-limits channel renames, so true 1-minute channel-name updates are not reliable.
- The created channel denies `Connect` for `@everyone`, so members can see it without joining it.
- Running the command again reuses the already configured timer channel instead of creating duplicates.

### Adding objectives

The Objectives panel contains an `Add Objective` button.

When clicked, it opens an ephemeral wizard with 2 objective types:

- **Vortex**:
1. Select rarity (Common / Uncommon / Epic / Legendary)  
2. Set pop time (UTC, `HH:MM`)
3. Set map name
4. Notify before pop (5-60 minutes)
5. Confirm

- **Core**:
1. Select rarity (Common / Uncommon / Epic / Legendary)
2. Set pop time (UTC, `HH:MM`)
3. Set map name
4. Notify before pop (5-60 minutes)
5. Confirm
- **Node**:
1. Select node type (Wood / Hide / Ore / Fiber)
2. Select tier (4.4 / 5.4 / 6.4 / 7.4 / 8.4)
3. Set pop time (UTC, `HH:MM`)
4. Set map name
5. Notify before pop (5-60 minutes)
6. Confirm

After confirmation, the bot posts the objective as a separate message in the same channel as the objectives panel.

Objective message buttons:

- `Notify Me`: assigns a per-objective notification role to the clicker.
- `Remove Objective`: removes the objective early (Admins and configured Caller role(s)).

Objective notifications:

- When an objective is posted, the bot creates (or reuses) a mentionable role like `Vortex-Epic-12:36` or `Wood-8.4-13:44`.
- At the chosen lead time, the bot sends one ping message mentioning the role.
- When the objective pops, the bot deletes the notification role and the ping message.

Required permissions for notifications:

- **Manage Roles** (bot role must be above the created roles) for role creation and assignment.

### Objective lifecycle

- Objectives automatically “expire” after they pop: once the pop time is reached, the objective message is marked as popped and then removed ~60 seconds later.
- Manual removal is available via the `Remove Objective` button for Admins and members with configured Caller role(s).

## Registration and balances

### `/register <character_name>`

- Validates user against configured guild (Albion API check).
- Adds row to Players worksheet with:
	- Discord ID
	- Albion nickname
	- Silver (starts at `0`)
- Updates Discord nickname to Albion nickname.
- Adds configured Member role.

### `/bal [nickname]`

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

### `!create-comp <comp_message_id> <source_channel_id>`

Before using this command, it is necessary to create a comp message. A Comp message can consist of multiple parties and each party **MUST** start with the **Party** word.  

Single party comp message example:

```
Party 1
1. Tank
2. Support
3. DPS
4. Heal
```

Multiple parties comp message example:

```
Party 1
1. Tank
2. Support
3. DPS
4. Heal

Party 2
1. Tank
2. Support
3. DPS
4. Heal

Party Battle Mounts
1. Behemoth
2. Chariot
3. Balista
4. Venom Basilisk
```

In `Party ... thread` threads:

- `1` → sign up to role `1`
- `-` → sign out self
- `-1` → force sign out role `1` (caller/admin only)
- `@User 1` → force sign up mentioned user to role `1` (caller/admin only)

## Data files

- `configs/guilds_config.json`:
	- guild mapping + role config + persistent config message references
- `configs/role_reaction_config.json`:
	- per-server role reaction panels (emoji → role mapping + last sent message references)
- `configs/objectives_config.json`:
	- per-server objectives panel reference + active objectives list
- `google_sheet_credentials/credentials_links.json`:
	- per-server sheet and worksheet mapping
- `google_sheet_credentials/*_credentials.json`:
	- stored service account credentials

## Notes

- Enable **Developer Mode** in Discord to copy message/channel IDs for `!create-comp`.
- If you rename worksheet tabs in Google Sheets, update mapping via `/update-config` or relink with `/bot-link-google-sheet`.

## Recommendations from the bot author:

- Create a separate category for the bot setup and configuration.
- Create separate channels for each setup:
	- `#bot-updates`
  	- `#bot-setup`
	- `#tickets-setup`
  	- `#role-reacts-setup`
  	- `#comp-storage`

### `#bot-updates`

- Channel with updates where the message will be sent when the hosting server is restarted, and informs about new bot updates if there are any.

### `#bot-setup`

- Channel where `/bot-setup` and `/bot-link-google-sheet` commands should be used. Bot configuration persistent panel will be sent here as well.

### `#tickets-setup`

- Channel where the `/tickets-setup` command should be used. An interactive panel to manage and create new ticket panels will be sent here.

### `#role-reacts-setup`

- Channel where the `/role-reaction-setup` command should be used. The setup wizard and panel management messages are sent here.

### `#comp-storage`

- Channel where comp messages will be stored. Can send the `.!create-comp 1234567890 0987654321` message to the quick access comp creation command.
