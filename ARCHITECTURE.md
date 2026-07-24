# Architecture

Wingman is a small Python monolith. FastAPI serves the local web interface, aiogram owns the Telegram polling loop, SQLAlchemy persists data, and the OpenAI Responses API supplies conversation replies.

## Phase 1 request lifecycle

1. Telegram receives a text message.
2. The handler checks the numeric Telegram user ID against the configured owner ID.
3. An authorized message is stored in the database.
4. Recent conversation messages are loaded.
5. The model client sends a compact system prompt and recent messages to OpenAI.
6. The assistant response is stored and sent back to Telegram.

The web health route reads configuration and database status without exposing secrets.

## Context and data boundaries

Phase 1 uses recent raw messages only. Memory, retrieval, summaries, tool validation, and agent inspection are added in later phases. The model never receives API keys or Telegram tokens.

## Process lifecycle

The `wingman start` command runs the web server and Telegram polling in one asyncio process. The command stays in the foreground by default. Stop and restart use a small PID file and signals. A later phase will add dashboard lifecycle controls.

## Data model

The initial database has users, conversations, and messages. IDs are UUID strings. Messages retain the Telegram message ID when available. Domain records will be added with foreign keys and soft deletion as their features are implemented.

## Security boundary

The web server is local-only by default. Telegram authorization uses a numeric owner ID, never a username. Secrets come from environment variables in Phase 1 and are redacted from health output. Password sessions, encrypted secret storage, CSRF protection, rate limiting, and first-run setup are Phase 6 work.
