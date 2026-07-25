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

Phase 2 adds a memory service with ownership checks and allowed field validation. Memory changes are recorded as tool executions when they come through the model action interface. Telegram cards store their chat and message identifiers. Delete and confirm callbacks check ownership before changing a memory, and repeated callbacks are safe because the resulting state is durable.

## Context and data boundaries

Phase 1 uses recent raw messages only. Memory, retrieval, summaries, tool validation, and agent inspection are added in later phases. The model never receives API keys or Telegram tokens.

Phase 2 stores memories and agent run records. Retrieval and structured model actions will use these records in Phase 3.

Phase 3 adds one concise embedding per memory. SQLite stores vectors as JSON for local simplicity. Retrieval combines lexical overlap and semantic similarity when an embedding is available, then applies deterministic importance, confidence, and recency weights. Retrieval candidates and score components are stored for inspection.

Phase 4 keeps recent raw messages within configurable limits and rolls older messages into a durable summary. The summary stores the last message it covered, so the same messages are not summarized repeatedly. Pending state is separate from permanent memory and expires automatically. Each model call stores a structured request snapshot with system prompt, user prompt, added context, recent messages, and estimated tokens.

The actual Responses API request has three clear layers. Static profile, safety, and time instructions go through `instructions`. Dynamic memory, summary, and pending-state context goes through a separate developer message. Recent user and assistant messages are sent as history, with the current user message appearing once. The API-call page shows these same layers in the stored request snapshot.

Phase 5 stores planning entities in relational tables. The context builder includes a small upcoming window of saved places, unused ideas, planned events, and active reminders. A simple reminder worker polls one-time reminders and sends due items through Telegram, then marks successful delivery. No external discovery or autonomous browsing is used.

## Process lifecycle

The `wingman start` command runs the web server and Telegram polling in one asyncio process. The command stays in the foreground by default. Stop and restart use a small PID file and signals. A later phase will add dashboard lifecycle controls.

## Data model

The initial database has users, conversations, and messages. IDs are UUID strings. Messages retain the Telegram message ID when available. Domain records will be added with foreign keys and soft deletion as their features are implemented.

## Security boundary

The web server is local-only by default. Telegram authorization uses a numeric owner ID, never a username. Secrets come from environment variables in Phase 1 and are redacted from health output. Password sessions, encrypted secret storage, CSRF protection, rate limiting, and first-run setup are Phase 6 work.

Deleted Telegram cards use a two-step lifecycle. The callback immediately soft-deletes the memory and edits the card to show the deleted state. Before the next authorized text message is processed, the bot deletes those tombstones and marks their card records as cleaned. Telegram deletion failures leave the tombstone pending for a later retry.
