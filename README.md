# Wingman

Wingman is a private Telegram relationship assistant with a local administration interface. It stores conversation history and will later organize memories, places, events, and reminders.

## Current status

Phase 1 is implemented. It provides configuration, SQLite persistence, a local health page, Telegram owner authorization, and basic OpenAI conversation replies.

Phases 2 through 6 are implemented at core scope. Use `/remember a detail to save` in Telegram to create a visible memory card. Visit `http://127.0.0.1:8080/` for the dashboard. On first use, create the local administrator password. The dashboard links to memories, conversations, full API calls, health, retrieval, settings, and system controls.

Phase 5 adds planning at `http://127.0.0.1:8080/planning`. It stores places, saved ideas, events, and one-time reminders. The reminder worker sends due reminders to the owner through Telegram when the bot is configured. It does not search the web or discover restaurants automatically.

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

The default dashboard address is `http://127.0.0.1:8080/`. The health page is available at `http://127.0.0.1:8080/health`. PostgreSQL and Docker are not required for Phase 1.

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

`update` performs a safe fast-forward update only when the Git worktree is clean. The system page also provides backup, export, pause, resume, and update actions.

## Data and tests

The default SQLite database is `wingman.db` in the current directory. Override it with `WINGMAN_DATABASE_URL`. Run checks with

```bash
ruff check .
ruff format --check .
mypy wingman
pytest
```

Export and backups are available in the system page. JSON import, encrypted secrets, login rate limiting, and retention controls are still planned. See `SECURITY.md` for limitations.
