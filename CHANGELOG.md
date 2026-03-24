# Changelog

All notable changes to this project will be documented in this file.

This project aims to follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- (add upcoming changes here)

## [v0.1.0] - 2026-03-24

### Added

- Discord bot core with per-server setup and configuration:
  - `/bot-setup` to configure guild name + roles (caller/economy/member) and post a persistent configuration panel.
  - `/update-config` interactive config update panel for setup values.
- Google Sheets integration:
  - `/bot-link-google-sheet` to store service account credentials locally and link a sheet + worksheet names.
  - Lootsplit logging and balance history logging to the configured worksheets.
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

### Security

- Service account credentials and server configuration are stored as local JSON files on the machine hosting the bot. Treat the host as sensitive.

[Unreleased]: compare/v0.1.0...HEAD
[v0.1.0]: releases/tag/v0.1.0
