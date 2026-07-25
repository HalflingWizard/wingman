# Implementation plan

This plan follows the phases in `BUILD_SPEC.md`. The first release stays a small monolith with server-rendered pages and one local process.

Version `1.0.0` is the current baseline. Phases 1 through 6 are implemented at core scope. The remaining limitations are listed in the Phase 6 section.

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

Status complete

- Add places, saved ideas, events, reminders, and time-aware context.

Delivered in Phase 5

- Added places with addresses, descriptions, source URLs, atmosphere tags, and lifecycle statuses.
- Added saved date ideas linked to places.
- Added events with timezone, status, descriptions, and optional places.
- Added one-time reminders with Telegram delivery tracking.
- Added the `/planning` page with basic create forms and lists.
- Added upcoming planning context to Telegram turns.
- Added a small reminder worker that runs with the Telegram bot.
- Kept web discovery and restaurant search out of scope. Source URLs are manually saved only.

## Phase 6

Status core complete, with documented limitations

- Added local settings and system pages with navigation from every dashboard page.
- Added bot pause and resume controls. Paused mode keeps the bot connected and sends a short status reply.
- Added JSON export without embeddings or secrets.
- Added SQLite database backups with restrictive file permissions.
- Added safe fast-forward Git updates that refuse a dirty worktree.
- Added CLI PID status, stop, restart, and update support.
- Added retrieval explanations with query details, memory text, embedding availability, and score components.
- Added Phase 6 tests for export, backups, lifecycle state, and retrieval inspection.

Remaining limitations

- API keys and Telegram tokens remain environment-backed. The settings page masks them and does not change them.
- JSON import, login rate limiting, log viewing, and independent web and bot process controls are not complete.
- The dashboard update action does not restart the running process after an update.

## Decisions and assumptions

- SQLite is the default for local development and tests.
- PostgreSQL support will be added when the domain schema is stable enough to justify migrations.
- Secrets remain in environment variables. Encrypted API and Telegram secret storage remains future work.
- The web server binds to `127.0.0.1` by default.
- The bot does not start without both a token and an allowed Telegram user ID.
- OpenAI failures produce a short Telegram error and never create an invented assistant response.
- The web dashboard is intentionally local-only and unauthenticated. Do not expose it beyond the trusted machine.
- Embedding failures fall back to lexical retrieval. No live OpenAI calls are made by the test suite.

## Post-1.0 roadmap

The next update starts after the `1.0.0` baseline. These phases are planned work. They should be implemented in order and kept small enough that the application remains runnable after every phase.

### Conversation requirement for every phase

Wingman must still feel like a natural conversation between Matt and a thoughtful assistant. Internal actions such as retrieval, scoring, tool calls, embeddings, memory IDs, and database changes must stay invisible unless the owner is inspecting them in the dashboard.

The assistant should

- Use the owner's name naturally when it is useful.
- Use the current date, time, and conversation history to understand references such as today, last night, the date, or Sara's birthday.
- Ask at most one useful follow-up question at a time.
- Avoid turning every message into a memory workflow.
- Ask before saving an uncertain or broad preference.
- Connect a new observation to an existing memory before creating a duplicate.
- Explain suggestions in ordinary language rather than mentioning scores or retrieval.
- Preserve the distinction between what Matt observed, what Chloe said, and what the assistant infers.

### Phase 7

Status complete

Validated model tools and memory search

- Define Responses API tools for searching memories, reading memory notes, creating memories, adding notes, confirming memories, and updating existing memories.
- Add a read-only `search_memories` tool first. The tool must return owned records, relevant notes, source context, and a short reason for each match.
- Connect tool calls to `MemoryToolExecutor` through one application-controlled dispatcher.
- Keep ownership checks, input validation, transactions, audit records, and error handling in the application.
- Never let the model write directly to SQLAlchemy or receive unrestricted database access.
- Add tool-call request and result snapshots to the API-call inspector.
- Add tests for valid calls, invalid arguments, unknown memory IDs, ownership isolation, duplicate prevention, and failed transactions.

Delivered in Phase 7

- Added Responses API function definitions for memory search, memory creation, note creation, memory updates, and memory confirmation.
- Added an application-controlled Responses API tool loop with a bounded number of rounds.
- Connected model tool calls to the validated `MemoryToolExecutor` and existing audit records.
- Added read-only memory search results with memory text, status, confidence, importance, and notes.
- Kept memory deletion out of model tools. Deletion remains an explicit owner action through cards and the dashboard.
- Added tool names to request snapshots and tool arguments and results to response snapshots.
- Switched the default conversation and summary model to `gpt-5-nano` with low reasoning effort, low verbosity, sequential tool calls, and stateless responses.
- Stored the complete redacted main request snapshot, including model settings and full tool schemas.
- Added mocked tests for memory search and the Responses API tool loop.

Acceptance examples

- A question about jewelry can trigger a memory search when the initial retrieved context is weak.
- The model can find the existing Sara's birthday earring memory instead of creating a second copy.
- A failed tool call produces a natural response and does not invent a successful change.

### Phase 8

Status complete

Natural memory conversation and evidence collection

- Add a conversation policy for when to suggest a memory, when to ask permission, and when to remain conversational.
- Let the model propose a memory without saving it immediately when the preference is uncertain.
- Show a visible memory card only after the owner confirms or when an explicit `/remember` command is used.
- Let the model add an evidence note to an existing memory when a new detail supports it.
- Preserve evidence context such as the event, date, people present, source message, and what was directly observed.
- Detect likely duplicates before creating a new memory.
- Support a natural follow-up sequence with one question at a time.

Target conversation behavior

1. Matt says a date went well.
2. Wingman asks whether he wants to save the preference when the statement is broad or uncertain.
3. Matt confirms that Chloe likes fancy Italian restaurants.
4. Wingman asks a focused follow-up about the dress or jewelry.
5. Matt describes the black dress and silver accessories.
6. Wingman creates an observation memory for Matt's observation only.
7. Wingman asks for one useful detail about the earrings.
8. Matt describes the silver sphere earring.
9. Wingman checks the existing Sara's birthday memory.
10. Wingman adds a dated evidence note instead of creating a duplicate.

Acceptance requirements

- The bot remains natural when no memory action is needed.
- The bot never silently converts one observation into a confirmed preference.
- Every saved memory card has a clear delete action.
- Every note explains where and when the evidence came from when that information is available.

Delivered in Phase 8

- Added `propose_memory` for uncertain personal observations and preferences.
- Added pending memory proposals with expiration, confirmation, and dismissal behavior.
- Added exact proposal context to the next model turn so a clear yes can save the proposed statement.
- Added automatic source notes for model-created memories and notes linked to the current message.
- Added visible Telegram cards for memories created through model tools.
- Added tests for proposal state, dismissal, confirmation, source notes, and the natural tool flow.

### Phase 9

Status complete

Memory relationships, provenance, and context quality

- Add structured source context for memories and notes, including source message, conversation, event, date, and optional subject.
- Add evidence and contradiction handling so later observations can correct or qualify earlier ones.
- Improve retrieval with query intent, aliases, stemming, notes, source context, and separate ranking explanations.
- Retrieve memory notes with their parent memory when the note is the useful evidence.
- Distinguish stable profile context, conversation context, event context, and temporary context in the model payload.
- Add context quality checks that identify when useful retrieved context was ignored in the answer.
- Add scenario tests for jewelry, restaurants, dates, corrections, and duplicate memories.

Acceptance requirements

- The API inspector clearly shows static context, dynamic context, retrieved records, tool calls, and final messages as separate sections.
- A memory can be traced from the assistant response to the retrieved record and then to its notes and source message.
- Context is short enough to fit the configured budget and strong enough to support the answer.

Delivered in Phase 9

- Added the editable `prompts/wingman.md` conversation-style file with a configurable path.
- Kept application safety, privacy, memory, and tool rules outside the editable prompt.
- Added retrieved memory notes and source message IDs to dynamic model context.
- Added note details to retrieval inspection candidates.
- Added a heuristic context-usage summary to API response snapshots.
- Kept retrieval query and candidate data in fixed-height highlighted code panels with copy buttons.

### Phase 10

Status complete

Dashboard redesign and useful visual feedback

- Create a shared minimal visual system for all pages.
- Add Font Awesome icons with accessible labels and tooltips.
- Add a consistent sidebar or top navigation with active-page state.
- Add summary cards for bot status, database status, recent API calls, memory count, upcoming events, and pending reminders.
- Improve memories with readable cards, status badges, note timelines, source context, search, filters, and clear actions.
- Improve planning with separate views for places, ideas, events, and reminders.
- Improve retrieval inspection with readable score tables, expandable candidate details, and copy buttons.
- Keep long prompts and JSON in fixed-height scrollable panels.
- Add empty states, success messages, error messages, and mobile-friendly spacing.
- Keep the interface server-rendered unless a richer interaction is clearly needed.

Delivered in Phase 10

- Added a shared responsive dashboard shell with a dark sidebar, active-page state, summary cards, panels, badges, and mobile spacing.
- Added Font Awesome icons with visible labels and accessible navigation state.
- Redesigned the dashboard with useful counts and direct links to the main tools.
- Applied the shared layout to health, memories, planning, retrieval, API calls, conversations, settings, and system pages.
- Kept retrieval and API diagnostics in fixed-height highlighted code panels with copy buttons.

Acceptance requirements

- A new user can understand the dashboard without reading the source code.
- Every icon has a text label or accessible description.
- The most important information is visible without opening raw JSON.
- Detailed diagnostic information remains available when needed.

### Phase 11

Status planned

Reliability, evaluation, and release hardening

- Add conversation scenario fixtures for the target natural dialogues.
- Add mocked Responses API tool-call tests without live API credentials.
- Add regression tests for context usage and duplicate memory prevention.
- Add model cost estimates and tool-call counts to the API-call inspector.
- Add retries and timeouts for tool calls with clear user-facing errors.
- Add retention controls for old API snapshots and retrieval logs.
- Add a release checklist covering migrations, exports, backups, startup, port fallback, and Telegram behavior.
- Release the next update only after the natural conversation scenarios pass review.

## Next update priority order

1. Tool foundation and safe memory search.
2. Natural memory conversation and evidence notes.
3. Provenance and context quality.
4. Dashboard redesign with Font Awesome icons.
5. Evaluation, reliability, and release hardening.
