# Changelog

All notable changes to this project will be documented in this file.

This project aims to follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- (add upcoming changes here)

### Changed

- `/add-utc-timer` now refreshes its voice-channel name every 10 minutes instead of every minute to avoid Discord channel rename rate limits.

## [v1.1.4] - 2026-04-09

### Added

- New admin command `/add-utc-timer` that creates a voice channel displaying the current UTC time.

## [v1.1.3] - 2026-04-04

### Fixed

- Economy command responses that exceed Discord's message length limit are now split into multiple follow-up messages instead of failing.
- `/lootsplit` and `/get-negative-siphon` no longer error when the response content grows beyond 2000 characters.

## [v1.1.2] - 2026-04-03

### Changed

- Updated check interval for leave guild action: 300 seconds -> 180 seconds.

## [v1.1.1] - 2026-04-03

### Added

- Economy command:
  - Added `/get-negative-siphon` to mention all users with negative Siphon balance, ordered from most negative to least negative.

### Changed

- `/get-participants` now sorts participant names case-insensitively so names are grouped regardless of uppercase/lowercase differences.

## [v1.1.0] - 2026-04-03

### Changed

- Players worksheet schema now includes a fifth `Siphon` column alongside `Silver`.
- `/bal` panel improvements:
  - now shows the member's Discord avatar in the embed.
  - now shows a `Siphon` field read from the Players worksheet.
- `/lootsplit` command UX:
  - `Officer` and `Caller` now use Discord member selectors instead of manual nickname text.
  - selected `Officer` and `Caller` are resolved to their registered Players-sheet nickname when available, with Discord display name as fallback.
  - `Officer` is now optional and defaults to the member who runs the command.

## [v1.0.1] - 2026-04-02

### Changed

- Economy command UX:
  - `/bal` now supports checking another member with `/bal @User` instead of manual nickname entry.
  - `/bal` now responds with a balance panel that shows the requested member inside the panel and includes both formatted and raw balance values.
  - `/bal-add` and `/bal-remove` now respond with balance update panels instead of plain text messages.
  - Balance update panels now include the action summary plus `Reason`, `Old balance`, and `New balance` fields.

## [v1.0.0] - 2026-03-31

### Added

- Objectives:
  - New objective type: **Core** (rarities and wizard steps aligned with Vortex).
  - Objective notifications:
    - Wizard step to select **Notify before pop** (5–60 minutes).
    - Per-objective notification role + `Notify Me` button to opt-in.
    - One-time pre-pop ping, and automatic cleanup of the notification role and ping message when the objective pops.
- New slash commands:
  - `/get-participants` (battle participation lookup)
  - `/bal` (balance lookup)
  - `/clear` (admin-only message purge)

### Changed

- Command UX: migrated legacy prefix commands to slash commands (kept `!create-comp` as prefix-only).
- Albion API usage: standardized nickname lookup on `get_player_by_nickname` in features that previously used exact-search.
- Registration reliability: added retry behavior to reduce false negatives from stale Albion API `GuildName` responses.

### Fixed

- Objectives rarity display formatting.

## [v0.1.0] - 2026-03-24

### Added

- Discord bot core with per-server setup and configuration:
  - `/bot-setup` to configure guild name + roles (caller/economy/member), bot updates channel, and leave-guild action, then post a persistent configuration panel.
  - `/update-config` interactive config update panel for setup values (including leave-guild action).
- Google Sheets integration:
  - `/bot-link-google-sheet` to store service account credentials locally and link a sheet + worksheet names.
  - Lootsplit logging and balance history logging to the configured worksheets.
- Guild membership tracking:
  - Background audit every 5 minutes to detect when a player leaves the configured Albion guild.
  - Configurable action: kick from server, remove all roles, or do nothing.
  - Enforcement runs even if Google Sheets is not linked (role-based audit fallback).
- Ticket system:
  - `/tickets-setup` wizard to create/manage ticket panels for guild applications.
  - Ticket channels with open/close workflow and permission gating.
- Registration and economy commands:
  - `/register` to validate Albion character and write to Players worksheet.
  - `!bal`, `/bal-add`, `/bal-remove` for balance reads and manual adjustments.
  - `/lootsplit` to distribute lootsplit payouts and append history rows.
- Party comp tooling:
  - `!create-comp` and party thread sign-up/sign-out behavior.
- Role reaction panels:
  - `/role-reaction-setup` wizard to create panels that grant/remove roles based on reaction add/remove.
- Objectives panel:
  - `/set-objective-panel` to post/update a persistent objectives panel.
  - Objective wizard to post Vortex/Node objectives with automatic expiry after pop.

### Changed

- Players worksheet schema now has 4 columns: Discord ID, Albion Nickname, Is In Guild (YES/NO), Silver.
  - `/register` writes `Is In Guild=YES`.
  - Balance and lootsplit operations read/write Silver from column D.

### Security

- Service account credentials and server configuration are stored as local JSON files on the machine hosting the bot. Treat the host as sensitive.

[Unreleased]: compare/v1.1.4...HEAD
[v1.1.4]: releases/tag/v1.1.4
[v1.1.3]: releases/tag/v1.1.3
[v1.1.2]: releases/tag/v1.1.2
[v1.1.1]: releases/tag/v1.1.1
[v1.1.0]: releases/tag/v1.1.0
[v1.0.1]: releases/tag/v1.0.1
[v1.0.0]: releases/tag/v1.0.0
[v0.1.0]: releases/tag/v0.1.0
