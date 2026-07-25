# Implementation plan

This plan follows the phases in `BUILD_SPEC.md`. The first release stays a small monolith with server-rendered pages and one local process.

## Phase 1

Status complete

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

Status complete

- Add memories, validated memory actions, Telegram memory cards, and delete callbacks.
- Add the first memory management pages.
- Record agent runs and tool executions.

Delivered in Phase 2

- Added owned memory records with supported types, statuses, confidence, importance, soft deletion, and card references.
- Added validated create, update, delete, and confirm memory actions.
- Added tool execution audit records with input, output, status, and errors.
- Added agent run records with model, status, latency, response, and error fields.
- Added `/remember` Telegram cards with delete and inferred-memory confirmation callbacks.
- Added idempotent Telegram card synchronization records.
- Added a local `/memories` page with create, edit, delete, restore, and confirm controls.
- Added Phase 2 tests for ownership isolation, soft deletion, tool validation, audit records, web actions, and agent runs.

## Phase 3

Status complete

- Add embeddings, hybrid retrieval, memory notes, confirmation, card updates, and retrieval inspection.

Delivered in Phase 3

- Added configurable OpenAI embeddings using `text-embedding-3-small` by default.
- Added stored embedding text and JSON vectors with a SQLite compatibility migration.
- Added deterministic hybrid retrieval with lexical matching, semantic similarity, importance, confidence, and recency.
- Added compact static and dynamic context construction for model turns.
- Added memory notes and evidence updates.
- Added retrieval audit records and a local retrieval inspector page.
- Added delayed Telegram deletion. A deleted card first remains as an edited tombstone, then is removed before the next owner message.

## Phase 4

Status complete

- Add rolling summaries, token budgets, pending conversational state, and conversation inspection.

Delivered in Phase 4

- Added rolling conversation summaries with summary update history and a message cursor.
- Added configurable recent-message and context-token budgets.
- Added short-lived pending conversational state with expiration.
- Added editable and removable memory notes in the web memory page.
- Added a central dashboard with links to health, memories, conversations, API calls, and retrieval.
- Added a full API-call inspector showing stored prompts, context, recent messages, responses, token use, latency, and errors.
- Added conversation inspection with summaries and recent messages.
- Added Phase 4 tests for these interfaces and lifecycle behaviors.
- Updated the startup browser target to the dashboard and added navigation to the health page.
- Separated static instructions, dynamic context, and recent conversation history in the actual Responses API payload.
- Added formatted fixed-height scroll panels for full API request and response inspection.

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
- Phase 2 web routes are local and unauthenticated. Web authentication and CSRF protection remain Phase 6 work.
- Embedding failures fall back to lexical retrieval. No live OpenAI calls are made by the test suite.
