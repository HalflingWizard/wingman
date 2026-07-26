# Implementation plan

Wingman 3.0.0 is the current completed release. The project remains a small local monolith with a server-rendered dashboard, one Telegram bot process, SQLite persistence, and controlled OpenAI model access.

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

Planning records can be created through validated model tools when the owner clearly expresses save intent.

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
- No external restaurant search or web discovery is included
- Encrypted secret storage, retention controls, and public deployment are out of scope

## Next development sequence

The next work should use incremental 2.x phases. These are planning labels for the next development cycle, not separate release promises. Each phase should leave the application runnable and preserve natural conversation as the primary product requirement.

### Phase 2.1

Privacy-safe defaults and inbound message foundation

Status complete

- Replace personal example names in defaults, prompts, fixtures, examples, and documentation with neutral names such as Odysseus and Penelope.
- Search the repository for personal names before each release so private information is not shipped in defaults or tests.
- Introduce a normalized inbound message model with text, source type, attachments, transcription metadata, and source message identifiers.
- Keep ordinary text behavior unchanged while making future voice and multiple-file handling possible.
- Add a clear unsupported-media response for photos, videos, documents, and other media that are not implemented yet.

Delivered in Phase 2.1

- Replaced private example names with Odysseus, Penelope, and Helena across prompts, defaults, examples, and tests.
- Added a provider-neutral inbound message envelope with support for multiple temporary attachments and expiration metadata.
- Added a clear Telegram response for unsupported non-text media.
- Removed the one-follow-up constraint from the conversation guidance.
- Enabled multiple model tool calls when one message contains several valid actions.

### Phase 2.2

Telegram responsiveness and voice transcription

Status complete

- Show Telegram typing status as soon as an authorized message begins processing.
- Refresh the typing action while a slow model or transcription request is running, then stop naturally when the response is sent.
- Download Telegram voice messages through the bot API and send the audio to a configurable OpenAI transcription service.
- Feed the transcription through the same context, retrieval, memory, and response pipeline used for typed messages.
- Store the original voice source, transcript, and timestamps so the conversation and diagnostics remain traceable.
- Add mocked transcription tests, failure handling, size limits, timeout handling, and a user-facing transcription error.
- Keep an attachment collection in the normalized message path so later support can include multiple images or files without redesigning the conversation model.

Delivered in Phase 2.2

- Added Telegram typing status refreshes while transcription, embedding, summarization, and response operations are running.
- Added Telegram voice download and OpenAI Audio Transcriptions integration using `gpt-4o-mini-transcribe` by default.
- Kept voice audio in memory only and released the buffer immediately after transcription or failure.
- Added voice size limits, empty-transcript handling, and clear user-facing errors.
- Passed the transcript through the existing memory, retrieval, context, tool, and response flow.
- Added mocked transcription coverage.

### Phase 2.3

Dynamic planning tools and conversational capture

Status complete

- Add application-controlled tools for searching, creating, updating, and annotating places, saved ideas, events, and reminders.
- Search existing planning records before creating a duplicate.
- Allow partial records. Unknown address, date, time, city, or other fields remain explicitly unknown instead of blocking useful capture.
- Ask for missing information when it is needed, while continuing any other safe and useful actions from the same message.
- Separate casual mentions from save intent. Save concrete details when they are clearly useful, and ask before turning an uncertain plan into a committed event or reminder.
- Preserve provenance by linking planning records to the conversation and source message that created or updated them.
- Use safe confirmation thresholds for reminders, dates, and externally meaningful commitments.
- Include relevant planning records in dynamic context without turning every conversation into a planning workflow.
- Add tools for updating and adding notes to existing places, ideas, events, and reminders.

Delivered in Phase 2.3

- Added planning search, place creation, saved idea creation, event creation, and reminder creation tools.
- Added duplicate checks before creating planning records.
- Allowed places to be saved with unknown address and city fields.
- Added application validation for ownership, dates, times, linked places, linked events, and audit records.
- Added planning tool schemas to the Responses API request.
- Updated memory guidance so explicit save requests create memories directly and several valid memory actions can happen in one turn.

### Phase 2.4

Natural planning capture, cards, and cross-entity updates

Status complete

- Treat clear save intent as enough to save a useful place, idea, event, or reminder.
- Keep unknown optional fields empty instead of blocking a useful partial record.
- Keep ownership checks, audit records, source links, and duplicate prevention for every action.
- Show planning records as Telegram cards with readable details and delete controls.
- Keep technical parameters and storage metadata out of natural chat replies.
- Continue supporting field-level memory updates and note additions without replacing unrelated content.

Delivered in Phase 2.4

- Added persistent Telegram cards for places, saved ideas, events, and reminders.
- Added planning card delete controls with ownership checks and safe status changes.
- Made clear place-saving intent save directly, including places with unknown location details.
- Kept technical fields, confidence, importance, and record IDs out of normal assistant replies.
- Added concise natural save guidance so cards provide details and controls separately from chat.

### Phase 2.5

Multimodal-ready storage and diagnostics

Status complete

- Store inbound attachments as a collection with type, provider file ID, local metadata, transcript or analysis status, and source message linkage. Delete downloaded files shortly after the provider request and response finish, with cleanup on success, failure, and timeout.
- Keep text, transcription, and future media content separate so an image or file can later be sent to a model without changing the conversation contract.
- Add API-call diagnostics for transcription requests and future attachment requests without exposing credentials.
- Add size, count, content-type, and timeout limits before enabling additional media types.
- Keep photos, videos, and documents unsupported in this phase and return a clear explanation when received.

Delivered in Phase 2.5

- Added short-lived attachment metadata linked to the source conversation message.
- Added attachment expiration and processing status without storing audio bytes or local files.
- Added transcription API diagnostics with model, file metadata, byte count, latency, and retention status.
- Added cleanup helpers for any future temporary local attachment paths.
- Kept voice processing on the existing transcript pipeline and kept unsupported media rejected.

### Phase 2.6

Dashboard visual refinement

Status complete

- Establish one consistent rule for icons. Use them consistently with labels, or remove decorative icons from secondary panel headers.
- Improve memory cards with larger statement editing, clearer notes, and grouped actions.
- Improve planning forms and records with responsive cards, structured fields, and readable status rows.
- Present conversations as distinct user and assistant message bubbles.
- Keep API and retrieval diagnostics in the existing fixed-height highlighted code panels.
- Verify the shared dashboard layout at desktop and narrow screen widths.
- Redesign memory cards with a clear statement, status and confidence badges, visible notes, source context, and grouped actions.
- Give the add-memory form a large statement textarea and a clearer field layout.
- Improve note editing and deletion with readable rows and distinct primary and destructive actions.
- Present conversations as chat-style message bubbles, or use consistent sender colors and sender icons if the bubble layout is too complex.
- Redesign planning forms and records into visually distinct sections for places, ideas, events, and reminders.
- Keep the API calls and retrieval pages as the visual reference for diagnostic panels.
- Improve settings spacing and form hierarchy. Use password fields for credentials, allow pasting, never prefill actual secrets, and preserve current values when a secret field is blank.
- Treat copy prevention for password fields as a weak usability feature rather than a security boundary. Browser controls and developer tools can still expose user-entered values.
- Test the dashboard at narrow and wide viewport sizes and check keyboard labels, focus states, contrast, and form errors.

## Cross-phase acceptance requirements

- No private owner or relationship names appear in shipped defaults, prompts, fixtures, or examples.
- Typed and transcribed voice messages follow the same natural conversation path.
- Unsupported media receives a clear response and does not corrupt the conversation state.
- Planning records can be captured with incomplete information and improved later.
- Memory and planning updates modify the correct existing record without creating duplicates.
- The assistant can ask for missing information while still completing other safe actions from the same message, and it may perform multiple valid tool calls for one message.
- Model tools remain validated, audited, bounded, and ownership-checked.
- The dashboard makes primary actions obvious without hiding detailed diagnostics.
- Every phase has mocked tests for external API behavior and does not require live OpenAI credentials.
