# Wingman

Wingman is a private Telegram relationship assistant with a local administration interface. It stores conversation history and organizes memories, places, events, and reminders.

## Version

The current application version is `1.0.0`. This is the first stable baseline for the implemented local dashboard, Telegram bot, memory system, retrieval inspector, planning features, exports, backups, and lifecycle controls.

## Current status

The Phase 1 through Phase 6 implementation is included in version `1.0.0`. It provides configuration, SQLite persistence, the local dashboard, Telegram owner authorization, OpenAI conversation replies, memories, retrieval, planning, API-call inspection, exports, backups, and bot lifecycle controls.

Phase 7 is now implemented on top of the `1.0.0` baseline. The default conversation and summary model is `gpt-5-nano`, with low reasoning effort and concise output. The model can request validated memory searches and controlled memory changes. Tool calls are audited and shown in the API-call inspector. Memory deletion remains an explicit owner action.

Phase 8 adds natural memory proposals. The assistant can ask whether to save a personal observation, save it only after a clear yes, dismiss it after a no, and attach a source note to model-created memories.

Phases 2 through 6 are implemented at core scope. Use `/remember a detail to save` in Telegram to create a visible memory card. Visit `http://127.0.0.1:8080/` for the local dashboard. It links to memories, conversations, full API calls, health, retrieval, settings, and system controls.

Phase 5 adds planning at `http://127.0.0.1:8080/planning`. It stores places, saved ideas, events, and one-time reminders. The reminder worker sends due reminders to the owner through Telegram when the bot is configured. It does not search the web or discover restaurants automatically.

When a Telegram memory card is deleted, it first changes to a deleted message. The next owner message removes that old card from the chat.

## Next update roadmap

The next update begins with validated model tools for memory search and memory actions. Later phases will improve natural evidence-gathering conversations, memory provenance, context quality, and the dashboard visual design. The dashboard redesign will use a minimal visual style and Font Awesome icons with accessible labels.

Natural conversation is a release requirement. Wingman should ask focused questions, use the owner's name and time context naturally, compare new observations with existing memories, and avoid exposing retrieval or tool mechanics in Telegram.

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

The dashboard normally starts at `http://127.0.0.1:8080/`. If that port is busy, Wingman tries the next 19 ports and prints and opens the selected address. The health page is available at `/health`. PostgreSQL and Docker are not required.

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
