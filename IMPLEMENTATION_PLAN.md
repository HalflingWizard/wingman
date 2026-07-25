# Implementation plan

Wingman 2.0.0 is the current completed release. The project remains a small local monolith with a server-rendered dashboard, one Telegram bot process, SQLite persistence, and controlled OpenAI model access.

## Product requirements

Wingman should feel like a natural relationship assistant. It should use context when it genuinely helps, avoid saving every detail, ask focused follow-up questions, preserve the difference between facts and inferences, and keep internal retrieval and tool mechanics out of normal Telegram replies.

## Completed capabilities

### Conversation and context

- Telegram conversation handling for one authorized owner
- Recent message history with rolling summaries
- Static owner-editable guidance in `prompts/wingman.md`
- Protected application safety, privacy, memory, identity, and time rules
- Dynamic context assembled from memories, notes, summaries, proposals, and relevant planning records
- Configurable message and context-token budgets
- Current date, time, timezone, owner name, and primary person name in the model instructions

### Memory

- Owned memories with facts, observations, inferences, preferences, confidence, importance, and status
- Hybrid lexical and semantic retrieval
- Stop-word filtering and related word matching
- Memory notes with evidence, confidence, and source message IDs
- Duplicate-aware search before memory creation
- Natural memory proposals for uncertain personal observations
- Visible Telegram memory cards with confirmation and deletion controls
- Delayed Telegram tombstone cleanup after deletion
- Dashboard create, edit, delete, restore, confirm, and note management

### Planning

- Places with addresses and descriptions
- Saved ideas
- Events with time and timezone
- One-time reminders with Telegram delivery tracking
- Dashboard planning page
- Relevant upcoming planning context in conversations

The model does not currently create places or events directly. Those actions remain explicit dashboard or application actions.

### Model tools and diagnostics

- OpenAI Responses API integration using `gpt-5-nano` by default
- Low reasoning effort and concise output configuration
- Validated sequential memory tool calls
- Bounded tool loop with ownership checks and audit records
- Complete request and response snapshots without credentials
- API-call page with prompts, context, tools, responses, token use, latency, errors, highlighting, scrolling, and copy buttons
- Retrieval inspector with query details, candidate text, ranking components, notes, source IDs, and copyable JSON

### Dashboard and operations

- Responsive local dashboard with shared navigation and Font Awesome icons
- Dashboard overview with counts and direct tool links
- Health, memories, context, conversations, planning, retrieval, API calls, settings, and system pages
- Local settings editing for selected runtime values and credentials
- Masked secrets with plaintext `.env` storage for local use
- Bot pause or resume toggle
- Versioned JSON export and import
- SQLite database backups with restrictive permissions
- Safe fast-forward Git updates
- CLI start, stop, restart, status, doctor, and update commands
- Port fallback when the configured web port is unavailable

## Data boundary

SQLite is the default database. The web dashboard and bot run locally. JSON export includes user-owned conversations, messages, summaries, memories, notes, places, ideas, events, and reminders. It excludes embeddings and secrets. Import preserves IDs where possible and assigns imported records to the current owner.

## Validation

Run the full validation suite from the project root

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy wingman
.venv/bin/pytest
```

The test suite covers configuration, persistence, Telegram authorization, memory ownership, retrieval, context construction, tool execution, proposals, dashboard pages, import, export, settings, lifecycle controls, and diagnostics.

## Known boundaries

- The dashboard is local-only and unauthenticated
- Credentials are plaintext in `.env`
- The project is intended for one trusted owner
- The model does not directly create places, events, or reminders
- No external restaurant search or web discovery is included
- Encrypted secret storage, retention controls, and public deployment are out of scope
