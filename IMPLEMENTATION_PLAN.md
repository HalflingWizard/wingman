# Implementation plan

This plan follows the phases in `BUILD_SPEC.md`. The first release stays a small monolith with server-rendered pages and one local process.

## Phase 1

Status in progress

- Set up a Python package and command line entry point.
- Add environment based configuration with safe local defaults.
- Add a SQLAlchemy database with users, conversations, and messages.
- Add database initialization on startup.
- Add a FastAPI health page.
- Add an aiogram Telegram connection with an owner user ID allowlist.
- Add a basic OpenAI Responses API conversation path.
- Persist every accepted Telegram user and assistant message.
- Add tests for configuration, persistence, authorization, and the health page.

## Phase 2

- Add memories, validated memory actions, Telegram memory cards, and delete callbacks.
- Add the first memory management pages.
- Record agent runs and tool executions.

## Phase 3

- Add embeddings, hybrid retrieval, memory notes, confirmation, card updates, and retrieval inspection.

## Phase 4

- Add rolling summaries, token budgets, pending conversational state, and conversation inspection.

## Phase 5

- Add places, saved ideas, events, reminders, and time-aware context.

## Phase 6

- Add authenticated settings, lifecycle controls, safe updates, export, backups, complete tests, and final security review.

## Decisions and assumptions

- SQLite is the default for local development and tests.
- PostgreSQL support will be added when the domain schema is stable enough to justify migrations.
- Phase 1 keeps secrets in environment variables. Encrypted secret storage and first-run setup belong to Phase 6.
- The web server binds to `127.0.0.1` by default.
- The bot does not start without both a token and an allowed Telegram user ID.
- OpenAI failures produce a short Telegram error and never create an invented assistant response.
