# Architecture

Wingman 5.10.0 is a small Python monolith. FastAPI serves the local dashboard, aiogram runs the Telegram polling loop, SQLAlchemy manages persistence, and the OpenAI Responses API generates conversation replies and embeddings.

The application is designed for one trusted owner on one machine. It favors clear boundaries and inspectable state over distributed services or a separate frontend application.

## Request lifecycle

1. Telegram receives a message.
2. The handler checks the numeric Telegram user ID against the configured owner ID.
3. The authorized message is stored in SQLite.
4. Text is normalized directly, while voice audio is downloaded into memory and transcribed.
5. The conversation, summary, and pending state are loaded. Saved records remain in the database.
6. The context builder creates separate static instructions, dynamic context, and recent message history.
7. The first OpenAI Responses API step must make an explicit saved-context retrieval decision. The model selects relevant categories and a semantic query.
8. The application runs hybrid search across memories, places, ideas, events, and reminders, then returns only ranked matches to the same model.
9. The application validates later actions, prevents repeated writes within the turn, preserves the original request and all tool results, and continues the bounded tool loop.
10. The assistant response is stored and sent to Telegram.

The web dashboard reads the same local state and exposes controls for memories, context, planning tabs, diagnostics, settings, location and timezone, backups, import, export, and bot lifecycle.

## Context model

Static context contains owner-editable conversation guidance from `prompts/wingman.md`, followed by application-controlled safety, privacy, memory, identity, and time rules. The editable guidance controls style only and cannot override application policy.

Dynamic context is built for each message. It contains rolling conversation summaries and temporary turn state. Saved records are not preloaded into this context. The agent retrieves a small relevant set through the unified search tool.

Recent messages remain separate from dynamic context. The current user message appears once in the API request. The API-call inspector stores these layers so the owner can understand what the model received.

## Memory and retrieval

Memories belong to the configured owner and support types, statuses, confidence, importance, soft deletion, notes, and Telegram card references. Memory notes preserve evidence, context, and source message IDs without requiring duplicate memory records.

Retrieval uses one `search_saved_context` tool across personal memories, places, ideas, events, and reminders. The first agent step is required to use this tool, while the model chooses the semantic query, relevant categories, filters, and whether ranked search or a list is needed. Missing vectors for existing records are generated lazily. Cosine similarity, normalized lexical overlap, and recency rank candidates. Weak candidates are rejected.

The complete original user input, every function call, and every function result remain in the Responses API input during later tool rounds. The model can refine a weak search, broaden categories, and ground the final answer in all retrieved results. Retrieval logs include routing decisions, category filters, candidate text, score components, selected records, and failures.

The active agent saves useful durable observations directly. Memory tools are application-controlled, ownership-checked, schema-validated, audited, and bounded by the model loop. Deletion remains an owner-controlled Telegram card or dashboard action.

## Planning

Places, saved ideas, events, and one-time reminders use relational tables. The model searches planning records when a request needs them. A small reminder worker sends due reminders through Telegram and records delivery state.

The model can use validated planning tools to search, create, and update places, saved ideas, events, and reminders. Planning tools check ownership, reject invalid links and dates, avoid exact duplicates, and allow places to be saved before an address or city is known. Deletion remains an owner-controlled Telegram card or dashboard action.

## Dashboard

The dashboard is server-rendered by FastAPI. A shared responsive layout provides navigation, Font Awesome icons, summary cards, status badges, forms, and mobile spacing. Long prompts, request payloads, responses, and retrieval JSON use fixed-height, scrollable, highlighted panels with copy buttons.

The Context page edits versioned prompt sections, shows read-only runtime context, and previews the combined instructions and dynamic context used by the agent. Prompt configuration is loaded from disk on every new request so dashboard changes apply without a restart. The Settings page persists selected runtime settings in the local `.env` file. The System page controls bot pause or resume, database backups, versioned JSON export and import, and safe Git updates.

Telegram voice messages are downloaded into memory, sent to the configured Audio Transcriptions model, and then released. Audio is not written to the database or retained as a project file. Supported documents are sent as temporary file inputs. Supported videos are downloaded temporarily, split into audio and five sampled frames, then deleted after processing. Only attachment metadata is persisted.

## Persistence and portability

SQLite is the default database. IDs are UUID strings. Export files use a version field and include conversations, messages, summaries, memories, notes, places, ideas, events, and reminders. Import preserves record IDs where possible, updates existing records, and forces imported ownership to the current local user.

Database backups are copied to the configured data directory with mode `0600`. JSON exports intentionally exclude embeddings and secrets.

## Process lifecycle

`wingman start` runs the web server and Telegram polling in one asyncio process. The dashboard can pause or resume message processing without stopping the web server. The CLI provides start, stop, restart, status, doctor, and safe update commands. The web server tries nearby ports when the configured port is busy.

## Security boundary

The dashboard binds to `127.0.0.1` by default and is intentionally unauthenticated. Telegram authorization uses a numeric owner ID. API keys and Telegram tokens are masked in the dashboard but are stored as plaintext environment values when configured locally. Do not expose the dashboard publicly or commit `.env`, database files, logs, exports, or backups.
