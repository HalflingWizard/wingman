# Wingman

Wingman is a private Telegram relationship assistant with a local administration interface. It stores conversation history and will later organize memories, places, events, and reminders.

## Current status

Phase 1 is implemented. It provides configuration, SQLite persistence, a local health page, Telegram owner authorization, and basic OpenAI conversation replies.

Phase 2, Phase 3, and Phase 4 are implemented. Use `/remember a detail to save` in Telegram to create a visible memory card. Visit `http://127.0.0.1:8080/` for the dashboard. It links to memories, conversations, full API calls, health, and retrieval. The web pages are not authenticated yet.

When a Telegram memory card is deleted, it first changes to a deleted message. The next owner message removes that old card from the chat.

## Requirements

- Linux with Python 3.12
- A Telegram bot token from BotFather
- The numeric Telegram user ID of the owner
- An OpenAI API key for conversation replies

## Install

```bash
git clone <repository>
cd wingman
./scripts/install.sh
source .venv/bin/activate
wingman doctor
wingman start
```

The default local address is `http://127.0.0.1:8080/health`. PostgreSQL and Docker are not required for Phase 1.

Copy `.env.example` to `.env` and fill in the Telegram and OpenAI values. Find a Telegram user ID with a trusted Telegram ID bot, then check that the value is numeric before saving it.

## Commands

```bash
wingman start
wingman start --no-browser
wingman stop
wingman restart
wingman status
wingman update
wingman doctor
```

`update` is reserved for the safe fast-forward update flow in Phase 6. The Phase 1 command reports that it is not yet available.

## Data and tests

The default SQLite database is `wingman.db` in the current directory. Override it with `WINGMAN_DATABASE_URL`. Run checks with

```bash
ruff check .
ruff format --check .
mypy wingman
pytest
```

Backups, import and export, encrypted secrets, and retention controls are planned for Phase 6. See `SECURITY.md` for limitations.
