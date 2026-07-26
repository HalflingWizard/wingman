# Architecture

Wingman 4.1.0 is a small Python monolith. FastAPI serves the local dashboard, aiogram runs the Telegram polling loop, SQLAlchemy manages persistence, and the OpenAI Responses API generates conversation replies and embeddings.

The application is designed for one trusted owner on one machine. It favors clear boundaries and inspectable state over distributed services or a separate frontend application.

## Request lifecycle

1. Telegram receives a message.
2. The handler checks the numeric Telegram user ID against the configured owner ID.
3. The authorized message is stored in SQLite.
4. Text is normalized directly, while voice audio is downloaded into memory and transcribed.
5. The conversation, summary, pending state, and relevant memories are loaded.
6. The context builder creates separate static instructions, dynamic context, and recent message history.
7. The OpenAI Responses API receives the request and may request multiple validated memory actions.
8. The application validates and executes allowed tool calls, records them, and continues the bounded tool loop.
9. The assistant response is stored and sent to Telegram.

The web dashboard reads the same local state and exposes controls for memories, context, planning, diagnostics, settings, backups, import, export, and bot lifecycle.

## Context model

Static context contains owner-editable conversation guidance from `prompts/wingman.md`, followed by application-controlled safety, privacy, memory, identity, and time rules. The editable guidance controls style only and cannot override application policy.

Dynamic context is built for each message. It can contain relevant saved memories, memory notes and source references, recent messages, rolling conversation summaries, pending memory proposals, and relevant planning records. The builder keeps the result within the configured context budget.

Recent messages remain separate from dynamic context. The current user message appears once in the API request. The API-call inspector stores these layers so the owner can understand what the model received.

## Memory and retrieval

Memories belong to the configured owner and support types, statuses, confidence, importance, soft deletion, notes, and Telegram card references. Memory notes preserve evidence, context, and source message IDs without requiring duplicate memory records.

Retrieval combines normalized lexical matching with semantic similarity when an embedding is available. Deterministic importance, confidence, and recency weighting produces ranked candidates. Query data, candidate text, score components, notes, and source IDs are recorded in retrieval logs for dashboard inspection.

Uncertain personal observations can become pending proposals. The owner can accept or dismiss a proposal. Memory tools are application-controlled, ownership-checked, schema-validated, audited, and bounded by the model loop.

## Planning

Places, saved ideas, events, and one-time reminders use relational tables. Upcoming planning records can contribute to dynamic context. A small reminder worker sends due reminders through Telegram and records delivery state.

The model can use validated planning tools to search and create places, saved ideas, events, and reminders. Planning tools check ownership, reject invalid links and dates, avoid exact duplicates, and allow places to be saved before an address or city is known. More complex planning updates remain explicit dashboard actions until their conversational policy is designed.

## Dashboard

The dashboard is server-rendered by FastAPI. A shared responsive layout provides navigation, Font Awesome icons, summary cards, status badges, forms, and mobile spacing. Long prompts, request payloads, responses, and retrieval JSON use fixed-height, scrollable, highlighted panels with copy buttons.

The Context page edits static guidance and explains dynamic context at a high level. The Settings page persists selected runtime settings in the local `.env` file. The System page controls bot pause or resume, database backups, versioned JSON export and import, and safe Git updates.

Telegram voice messages are downloaded into memory, sent to the configured Audio Transcriptions model, and then released. Audio is not written to the database or retained as a project file. Supported documents are sent as temporary file inputs. Supported videos are downloaded temporarily, split into audio and five sampled frames, then deleted after processing. Only attachment metadata is persisted.

## Persistence and portability

SQLite is the default database. IDs are UUID strings. Export files use a version field and include conversations, messages, summaries, memories, notes, places, ideas, events, and reminders. Import preserves record IDs where possible, updates existing records, and forces imported ownership to the current local user.

Database backups are copied to the configured data directory with mode `0600`. JSON exports intentionally exclude embeddings and secrets.

## Process lifecycle

`wingman start` runs the web server and Telegram polling in one asyncio process. The dashboard can pause or resume message processing without stopping the web server. The CLI provides start, stop, restart, status, doctor, and safe update commands. The web server tries nearby ports when the configured port is busy.

## Security boundary

The dashboard binds to `127.0.0.1` by default and is intentionally unauthenticated. Telegram authorization uses a numeric owner ID. API keys and Telegram tokens are masked in the dashboard but are stored as plaintext environment values when configured locally. Do not expose the dashboard publicly or commit `.env`, database files, logs, exports, or backups.
