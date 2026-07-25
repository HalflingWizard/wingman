# Architecture

Wingman is a small Python monolith. FastAPI serves the local web interface, aiogram owns the Telegram polling loop, SQLAlchemy persists data, and the OpenAI Responses API supplies conversation replies.

The current application version is `1.0.0`. It represents the first stable baseline after Phases 1 through 6.

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

## Post-1.0 direction

The post-1.0 implementation adds a controlled model tool loop. The model may request a memory search or a memory change, but the application validates every request, checks ownership, performs the transaction, records the tool execution, and returns a limited result. The model never receives direct database access. The loop is bounded so a response cannot make unlimited tool calls.

The default conversation and summary model is `gpt-5-nano`. Main responses use low reasoning effort, low verbosity, sequential function calls, `store=false`, and encrypted reasoning content for stateless follow-up requests. The API-call inspector stores the complete request configuration and tool definitions without API credentials.

Memory retrieval and memory actions are separate concerns. Search is read-only and can be used when the initial context is insufficient. Memory creation, confirmation, updates, and note changes require stronger application rules. Uncertain preferences should be proposed conversationally and confirmed by Matt before becoming confirmed memories.

Memories will gain stronger provenance. A useful memory should be connected to the message, conversation, event, date, or observation that supports it. Notes should preserve additional evidence instead of creating duplicate memories. The assistant should use that structure to ask natural follow-up questions and compare new observations with existing context.

Phase 8 begins this provenance flow. A personal observation can become a pending memory proposal instead of an immediate write. The proposal expires, can be dismissed, and is completed only after a clear owner confirmation. Model-created memories receive a source note linked to the current message, and visible Telegram cards keep the owner aware of the saved result.

Phase 9 separates editable conversation style from application policy. The owner can change `prompts/wingman.md`, while safety, privacy, memory validation, and tool rules remain in code. Retrieved memories carry their notes and source message IDs into dynamic context. The API response snapshot includes a simple word-overlap check showing which retrieved memory statements were mentioned in the answer.

The dashboard is a shared visual workspace. It uses a small responsive style system, Font Awesome icons with accessible labels, readable memory records, useful status summaries, and diagnostic details. Raw JSON and prompt content remain available in fixed-height, scrollable, copyable inspection panels. The interface stays server-rendered so the local app has no frontend build step.

The Context page separates owner-editable conversation guidance from application-controlled safety and tool rules. It also explains the dynamic context sources without exposing retrieval internals to the model. The Settings page can persist selected runtime values in the local `.env` file. API keys are accepted for local convenience but remain plaintext on disk and masked in the interface.

JSON export and import use versioned user data. Imports preserve record IDs where possible, update existing records, and force ownership fields to the currently configured owner so an export cannot introduce another owner through the web form.

## Process lifecycle

The `wingman start` command runs the web server and Telegram polling in one asyncio process. The command stays in the foreground by default. Stop and restart use a small PID file and signals. The dashboard can pause or resume Telegram message processing without stopping the web server. Full independent process control remains future work.

## Data model

The initial database has users, conversations, and messages. IDs are UUID strings. Messages retain the Telegram message ID when available. Domain records will be added with foreign keys and soft deletion as their features are implemented.

## Security boundary

The web server is local-only by default and the dashboard is intentionally unauthenticated. Telegram authorization uses a numeric owner ID, never a username. Secrets come from environment variables and are redacted from health and settings pages. Encrypted secret storage remains future work.

Deleted Telegram cards use a two-step lifecycle. The callback immediately soft-deletes the memory and edits the card to show the deleted state. Before the next authorized text message is processed, the bot deletes those tombstones and marks their card records as cleaned. Telegram deletion failures leave the tombstone pending for a later retry.
