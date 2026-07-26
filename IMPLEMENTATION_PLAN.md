# Implementation plan

Wingman 5.9.0 is the current completed release. The project remains a small local monolith with a server-rendered dashboard, one Telegram bot process, SQLite persistence, and controlled OpenAI model access.

## Phase 5.9 completed

- Kept runtime output bounded to the latest 100 lines.
- Added live log copy, clear-view, pause, and line-wrap controls.
- Added stale temporary attachment cleanup for interrupted processes.
- Preserved attachment cleanup after normal success and failure paths.
- Added regression coverage for cleanup and observability controls.

## Phase 5.8 completed

- Replaced the planning grid with Places, Saved ideas, Events, and Reminders tabs.
- Added section search, add forms, record cards, edit forms, and current status badges.
- Added explicit confirmation before dashboard hard deletion.
- Kept deleted records hidden by default with a Show deleted control.
- Added persisted local location settings alongside timezone settings.
- Preserved city autocomplete and timezone selection in the local settings page.

## Phase 5.7 completed

- Added timezone-aware date filters to memory and planning searches.
- Resolved common periods such as yesterday, last week, last month, and this month.
- Added planning filters for item type and city.
- Included Telegram reply context in the agent context.
- Included structured owned record context when the user replies to a memory or planning card.
- Passed exact card record IDs to the model for updates without exposing them in normal replies.

## Phase 5.6 completed

- Reduced the active model tool set to direct memory and planning operations.
- Removed proposal, confirmation, note-only, and action-registration tools from normal agent requests.
- Added one ownership-checked `update_planning_item` tool for places, ideas, events, and reminders.
- Added validated service updates for saved ideas, events, and reminders.
- Kept the bounded eight-round primary-agent loop and parallel tool calls.
- Added per-turn idempotency protection for repeated memory and planning writes.
- Kept deletion under Telegram cards and dashboard controls.

## Phase 5.5 completed

- Replaced the single context textarea with organized editable prompt sections.
- Added active prompt configuration persistence with version ID, version number, timestamp, active status, and updater metadata.
- Added read-only personal context and system capability information to the dashboard.
- Added a combined prompt preview using the same context and instruction builders as real agent requests.
- Reloaded the active prompt configuration from disk for every new request.

## Phase 5.4 completed

- Added query embeddings to model-directed memory searches.
- Combined cosine similarity with normalized keyword overlap, importance, confidence, and recency.
- Added relevance thresholds that reject weak name-only matches.
- Preserved lexical fallback when memory embeddings are unavailable or an embedding request fails.
- Kept normal tool selection automatic instead of forcing memory search on every request.
- Added retrieval and tool-path regression tests.

## Phase 5.3 completed

- Made the first memory search mandatory before every model response when tools are available.
- Kept all other tool selection automatic.
- Allowed empty memory results to fall back to the recent conversation and general knowledge.

## Phase 5.2 completed

- Added `/ideas` and `/reminders` Telegram commands.
- Added paginated five-item menus for all four planning record types.
- Added full detail cards for selected ideas and reminders.
- Recorded verified planning selections as user-context messages for the next model request.

## Phase 5.1 completed

- Added `/places` and `/events` Telegram commands.
- Added five-item paginated inline menus with Previous and Next controls.
- Added full detail cards for selected places and events, including the existing delete control.
- Added ownership checks before listing, viewing, or deleting planning records.

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

The completed 2.x work is recorded below. The next work uses incremental 3.x phases. These are planning labels for the next development cycle, not separate release promises. Each phase should leave the application runnable and preserve natural conversation as the primary product requirement.

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

## Version 3.x roadmap

The next release family will improve action reliability first, then add multimodal conversation, usage accounting, and controlled development automation. The action coordinator is intentionally first because memories, planning records, image analysis, document reading, and video processing all need the same completion and recovery rules.

### Phase 3.1

Action extraction and pending action ledger

Status complete

- Extract every requested memory, note, planning action, and future media action from one user message.
- Assign every action a stable ID and store its type, source message, target entity, arguments, and status.
- Track pending, completed, duplicate, needs clarification, failed, dismissed, and blocked states.
- Store the complete pending action group so replies such as “yes”, “save those”, or “save the first and third” resolve against the original list.
- Make action records durable across turns and process restarts.
- Keep action state separate from the assistant’s natural response text.

Delivered

- Added durable action groups and action items with source message, stable action ID, status, result, and error fields.
- Added action ledger lookup and grouped confirmation across turns.

### Phase 3.2

Bounded action completion coordinator

Status complete

- Replace the current model-only continuation behavior with an application-controlled completion loop.
- Execute valid actions, record the results, inspect the remaining action ledger, and continue when work remains.
- Treat duplicates as handled and retry safe failures only when the retry policy allows it.
- Stop only when all actions are completed, duplicated, dismissed, blocked, or require information from the owner.
- Add maximum rounds, action count, tool call count, token, time, and retry limits.
- Prevent duplicate execution with action IDs and idempotency checks.
- Record every continuation round in API diagnostics.
- Generate the final response from actual action state rather than trusting the model to claim completion.

Delivered

- Added an eight-round application-controlled continuation loop.
- The loop checks pending action state and continues without asking the owner to repeat the request.
- Tool execution results are written back to the ledger with completion, duplicate, clarification, or failure status.

### Phase 3.3

Natural multi-action confirmations and cards

Status complete

- Save several explicit details in one turn without asking for permission again.
- Confirm a complete proposal group when the owner says “yes”.
- Resolve partial confirmations such as “save cats and Hello Kitty” without reopening unrelated items.
- Ask only about unresolved or ambiguous items.
- Keep parameters, counts, confidence values, IDs, and database operations out of normal replies.
- Show a Telegram card for every successfully created memory or planning record.
- Keep deletion and later editing tied to the correct action and entity IDs.
- Add regression tests for partial saves, repeated confirmations, duplicates, retries, and restart recovery.

Delivered

- Added grouped registration and confirmation tools to the Responses API tool set.
- Added action IDs to memory and planning write tools.
- Added current action ledger context to the next conversation turn.
- Kept normal replies focused on natural conversation while cards remain responsible for record details and controls.

### Phase 3.4

Database consistency and dashboard freshness

Status complete

- Reproduce cases where a Telegram memory card exists but the dashboard does not show the record.
- Verify the active database path, owner ID, process working directory, settings cache, and transaction boundaries used by Telegram and FastAPI.
- Show safe diagnostic information in the dashboard so the active database and owner scope can be compared without exposing secrets.
- Make dashboard reads use the same configured settings and database source as the bot.
- Add refresh behavior after writes and an optional manual refresh indicator with the last-read time.
- Add tests that create records through the Telegram service path and immediately read them through dashboard routes.

Delivered

- The CLI now passes the exact startup settings object into the dashboard app, keeping bot and dashboard database configuration aligned.
- Dashboard reads send no-cache headers and include a manual refresh control with a visible read timestamp.
- The dashboard shows the active database path and owner-scope counts, while the System page shows safe database diagnostics.
- Added regression tests covering Telegram service writes, immediate dashboard visibility, cache headers, and diagnostic scope output.

### Phase 3.5

Image messages and multimodal request foundations

Status complete

- Accept image-only messages and image messages with a caption.
- Support up to five images per message by default, with a safe configurable maximum of ten.
- Preserve image order, captions, provider IDs, media type, dimensions, and expiration metadata.
- Send images and captions to the model as multimodal input while keeping memory retrieval, planning tools, and natural replies unchanged.
- Let the model infer intent from screenshots, conversation captures, photos, and other allowed images without requiring a special command.
- Enforce per-file size, total message size, count, content-type, and timeout limits.
- Delete downloaded image files after the model response or failure and never retain image bytes in the database.
- Add image diagnostics that record metadata and usage without storing raw image content in request snapshots.

Delivered

- Added Telegram image and media-group handling with caption support and a default five-image limit.
- Added per-image and total byte limits, ordered temporary attachments, and cleanup after processing.
- Added multimodal Responses API input using ordered text and image content parts.
- Added image metadata fields for provider ID, size, dimensions, media type, and expiration tracking.
- Added sanitized image diagnostics that omit raw image bytes from API snapshots.
- Added regression tests for image-only input, captioned images, diagnostics, and cleanup.
- Uses high image detail by default and accepts image files sent as Telegram documents to avoid photo compression when original quality matters.
- Added explicit image capability guidance so responses do not claim unsupported OCR, browsing, metadata, or external actions.

### Phase 3.6

Supported document attachments

Status complete

- Accept an explicit allowlist of readable formats, initially PDF, DOCX, TXT, Markdown, CSV, and JSON.
- Reject executables, archives, unsupported office formats, and unknown extensions with a clear user-facing message.
- Decide per format whether to use provider file input or local extraction, based on size, privacy, and API support.
- Preserve document name, type, size, page or character estimates, and processing status without retaining the local file.
- Send extracted or provider-readable content together with the caption and other message content.
- Apply character, size, and download timeout limits. Preserve page counts when a provider or future extractor supplies them.
- Add tests for valid files, invalid files, extraction failures, cleanup, and mixed image plus document messages.

Delivered

- Added an allowlist for PDF, DOCX, TXT, Markdown, CSV, and JSON Telegram documents.
- Added byte and UTF-8 character limits with clear rejection messages.
- Added a bounded document download timeout.
- Added temporary document files with cleanup after processing and metadata-only persistence.
- Added Responses API `input_file` parts with sanitized request diagnostics.
- Added regression coverage for supported and unsupported types, document input, metadata, and cleanup.

### Phase 3.7

Video understanding pipeline

Status complete

- Accept supported video messages within strict size and duration limits.
- Extract the audio track into a temporary buffer and transcribe it through the existing transcription path.
- Sample five frames from evenly distributed parts of the video, including the beginning and end when possible.
- Send the five ordered frames, the transcript, and the user caption to the model with explicit labels explaining what each input represents.
- Keep the video, extracted audio, and frame files temporary and delete them after success, failure, or timeout.
- Return a useful error when video processing tools are unavailable or the media cannot be decoded.
- Add diagnostics for duration, frame count, transcription status, model usage, and cleanup status without storing media bytes.

Delivered

- Added bounded MP4, MOV, M4V, and WebM video handling through Telegram.
- Added ffprobe validation, duration limits, and timeout-bounded ffmpeg processing.
- Added temporary audio extraction through the configured transcription model.
- Added five evenly distributed JPEG frame samples and ordered multimodal model input.
- Added sanitized video frame diagnostics and cleanup on success or failure.
- Added regression tests for mixed transcript and frame input and invalid video metadata.

### Phase 3.8

Cost and usage dashboard

Status complete

- Create a usage ledger for every model operation, including conversation replies, summaries, embeddings, transcription, image processing, document processing, and video processing.
- Record operation type, model, provider, timestamp, input and output tokens when available, media units, pricing version, estimated cost, and whether the value is reported or estimated.
- Add a cost page with daily totals, date filtering, model filtering, and a toggle between dollars and tokens or media units.
- Add a readable stacked bar chart with separate colors for replies, summaries, embeddings, transcription, images, documents, and video.
- Show a detailed table beneath the chart so every total can be audited back to an operation.
- Keep pricing data in a versioned application-controlled table and make unknown pricing visible instead of silently reporting zero.
- Never include API keys, raw media, or sensitive prompt content in the usage ledger.

Delivered

- Added a dashboard usage page with daily stacked cost bars and operation details.
- Added token totals, model grouping, operation classification, and current pricing estimates.
- Marked media operations without provider token counts as visible but not estimated.
- Added loaded repository commit, branch, and commit message information to the dashboard.
- Reworked rolling summaries around a ten-message short-term window and displaced-message boundary.
- Removed the old unsupported-media wording from the active Telegram message path.

### Phase 3.9

Ralph loop for controlled development

Status complete

The Ralph loop is an iterative development pattern, commonly associated with the Ralph Wiggum technique. A durable task list defines the work. Each iteration selects a task, gives the agent the current repository and task state, runs the implementation and verification steps, records the result, and continues only when the stop conditions allow it. The loop is persistence around a testable task list, not a replacement for product planning or human review.

For Wingman, use it first as a development and evaluation workflow rather than as a runtime bot feature.

- Store a versioned task ledger with acceptance criteria, dependencies, status, attempts, and verification results.
- Run one bounded task per iteration with repository checks, tests, and a clear token or time budget.
- Preserve progress, failures, and decisions between iterations without injecting hidden context into user conversations.
- Stop on repeated failures, unsafe file changes, missing credentials, failed tests, or tasks requiring human judgment.
- Require human review before merging or deploying changes.
- Add an evaluation suite for memory capture, multimodal understanding, planning actions, natural replies, cleanup, and cost accounting.
- Revisit whether a runtime self-review loop is useful only after the development loop proves safe and measurable.

Delivered

- Added a versioned development task ledger with acceptance criteria, dependencies, status, and verification commands.
- Added a human-gated development loop document with bounded iteration and stop conditions.
- Kept the loop separate from runtime conversations and user data.

### Phase 3.10

Multimodal integration and release hardening

Status complete

- Test mixed messages containing captions, multiple images, documents, and video metadata.
- Verify that multimodal turns still use relevant memories naturally and do not save every visual detail.
- Verify that all temporary files are deleted on success, model failure, timeout, cancellation, and process restart.
- Validate dashboard consistency, cost totals, diagnostics, privacy boundaries, and responsive layouts.
- Update the README, architecture notes, security notes, release notes, and configuration examples for the final 3.x release.

Delivered

- Fixed dashboard freshness for conversations and API calls with explicit latest-message queries and no-cache headers.
- Reviewed dashboard health, context, memory, planning, diagnostics, usage, settings, and system content.
- Added loaded commit and bot state information to health and dashboard views.
- Added release hardening regression coverage for current dashboard data.

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
- Multimodal inputs are bounded, traceable, and deleted after processing.
- Cost totals identify reported versus estimated usage and can be reconciled to individual operations.
- No autonomous development or runtime loop can bypass application validation, ownership checks, safety rules, or human review.

## Version 4.x roadmap

Each phase below is a release increment. Implementing Phase 4.1 produces version 4.1.0, implementing Phase 4.2 produces version 4.2.0, and so on. This roadmap preserves natural conversation, database verification, local privacy, and simple operation as acceptance requirements.

### Phase 4.1

Status complete

Reliable owner commands, conversation reset, and user-visible failures

- Add a concise `/newchat` command that closes the active conversation and starts a fresh one.
- Preserve memories, planning records, usage records, and diagnostics when a chat is reset.
- Add a natural `/remember` command path that classifies the supplied detail as a memory, place, event, idea, or reminder before saving it.
- Verify every command write in the database before showing its Telegram card.
- Add command help and visible command descriptions in Telegram.
- Increase voice-message limits safely with configurable size and duration limits, timeout handling, and cleanup tests.
- Send a clear Telegram error when media processing, transcription, or model response handling fails.
- Record detailed runtime errors with timestamps, source locations, exception types, tracebacks, and message IDs.
- Treat a model response timeout as a failed response and notify the owner instead of leaving the message unanswered.

### Phase 4.2

Status complete

Better memory retrieval and tool schema reliability

- Separate lexical exact-term matching, normalized keyword matching, and semantic similarity in retrieval diagnostics.
- Use a structured memory search query with keywords, a semantic sentence, optional entity hints, and status filters.
- Improve stemming, synonym handling, phrase matching, and score explanations without returning every memory by default.
- Establish documented allowed values for memory types, planning types, statuses, note types, and action types.
- Improve tool descriptions and schemas so the model uses the exact allowed values on its first attempt.
- Add retrieval evaluation cases for related terms such as jewelry, accessories, earrings, and silver.
- Keep dashboard diagnostics bounded to the latest 100 tool executions, agent runs, API calls, and runtime errors.
- Sample video frames away from the exact stream endpoint and validate that every frame has bytes before sending it to the model.
- Reject empty image and frame attachments before request construction so the Telegram error is clear and the API never receives an empty data URL.

### Phase 4.3

Status complete

Operational logs and failure history

- Replace the current tool-call-only logs page with a live last-100-lines runtime output view.
- Add a durable error history with timestamp, source, operation, user-safe message, exception type, file, line, traceback, and related agent or message IDs.
- Record received messages that time out or receive no response.
- Record processing failures without storing raw credentials or unnecessary media bytes.
- Add filtering by date, error type, operation, and severity.
- Keep live output bounded and make detailed errors copyable and scrollable.
- The removed sticker status work is intentionally not part of this release.

### Release hardening

Status complete

- Run the full automated test suite, lint, formatting, type checks, and diff checks.
- Verify dashboard routes, live logs, durable error history, and bounded diagnostic queries.
- Verify that tests clean up temporary planning records and media files.
- Keep release notes limited to the current release.

### Phase 4.4

Status complete

Model-directed retrieval and attachment intake hardening

- Stop preloading all memories and planning records into every model request.
- Require the model to use documented search tools when saved context is needed.
- Prevent unrelated high-importance memories from bypassing relevance matching.
- Classify Telegram files by MIME type and filename before selecting the processing path.
- Process video documents, audio files, animations, normal videos, and video notes through the appropriate pipeline.
- Persist the incoming dashboard message before media processing so failures remain visible.
- Record and report download, decoding, transcription, and media API failures with safe user-facing messages and detailed diagnostics.
- Add tests for model-directed retrieval, file classification, and early dashboard persistence.

## Version 5.x roadmap

Each phase below is a release increment. The current completed release is 5.9.0. The roadmap keeps the agent natural, keeps the dashboard as the context source of truth, and avoids unnecessary tool and prompt duplication.

### Phase 5.4

Hybrid retrieval and search quality

Status complete

- Replace the current keyword-only tool execution path with hybrid memory retrieval.
- Turn each memory-search query into an embedding using the configured embedding model.
- Compare the query embedding with stored memory embeddings using cosine similarity.
- Combine semantic similarity, normalized keyword overlap, phrase matches, recency, confidence, and importance into one transparent score.
- Return semantic similarity and keyword contributions in retrieval diagnostics.
- Apply minimum relevance thresholds so a shared name alone cannot make an unrelated memory appear relevant.
- Keep keyword retrieval as a useful fallback when embeddings are missing.
- Use a focused query based on the actual user request instead of allowing an empty or invented subject to dominate retrieval.
- Return memory statements and notes together with internal IDs for tool use.
- Remove mandatory memory search from every turn and return normal tool selection to `auto`.
- Strongly guide the model to search when saved context, prior history, or duplicate checking is relevant.

Acceptance requirements

- A query about pizza does not return memories only because they mention the person's name.
- A query about jewelry can match accessories through both semantic similarity and normalized terms.
- Retrieval diagnostics show the query, keywords, cosine similarity, keyword score, final score, and selected records.
- Tests cover missing embeddings, weak matches, close semantic matches, and keyword-only fallback.

### Phase 5.5

Dashboard-owned prompt and context architecture

Status complete

- Replace the current static and dynamic context layout with organized editable sections.
- Add Personality and safety, Memory and planning behavior, Tool orchestration, and Attachment capabilities sections.
- Add a read-only Personal context section with owner name, primary person name, timezone, current local time, and active model.
- Persist editable sections as versioned prompt configuration records.
- Mark exactly one prompt version as active.
- Invalidate stale prompt caches immediately after Save.
- Make every new model request load the active prompt version or a correctly refreshed cache.
- Build one shared final-context function for both real requests and dashboard preview.
- Add a Preview final agent context action showing the exact combined prompt and resolved runtime values.
- Remove repeated names, timezone text, examples, and duplicated rules from the final prompt.

Acceptance requirements

- A saved dashboard edit appears in the next agent request without restarting the process.
- The preview and the real request use the same context builder.
- Runtime personal values appear once in the final prompt.
- Old prompt versions can be inspected and the active version is visible.

### Phase 5.6

Simplified tools and reliable orchestration

Status complete

- Keep `search_memories`, `create_memory`, and `update_memory` as the memory tools.
- Remove proposal, confirmation, note-only, and action-registration tools from the active tool set.
- Keep `search_planning`, `create_place`, `create_saved_idea`, `create_event`, and `create_reminder`.
- Add one validated `update_planning_item` tool for places, ideas, events, and reminders.
- Keep deletion under user Telegram cards and dashboard controls.
- Update schemas with clear allowed values, optional fields, ownership rules, and date requirements.
- Use an async or otherwise safe embedding path when a model-generated search query reaches the hybrid retriever.
- Keep one primary agent with a bounded six to eight round tool loop.
- Execute parallel independent tool calls and return every result to the same agent.
- Add per-turn idempotency keys for all memory and planning writes.
- Prevent duplicate writes when the same call is repeated during one turn.

Acceptance requirements

- The active request contains only the current supported tool set.
- Multiple requested saves complete without proposal or confirmation loops.
- Updates modify the intended owned record and do not create duplicates.
- A maximum tool round failure is logged and reported clearly.

Implementation note

Legacy persistence and action-ledger helpers remain available for migration compatibility. They are not included in `AVAILABLE_TOOLS` and cannot be selected by normal model requests.

### Phase 5.7

Time-aware retrieval and Telegram reply context

Status complete

- Add date range, memory type, person, item type, city, and top-k filters to search tools.
- Resolve phrases such as last week, last June, yesterday, this month, and between May and July using the configured timezone.
- Search memories by meaningful occurrence time when available, not only creation time.
- Search places, ideas, events, and reminders using the correct record date fields.
- Include replied-to Telegram messages in the next agent input.
- Include structured memory and planning card context when the owner replies to a card.
- Provide internal record IDs to tools without exposing them in final replies.
- Avoid repeating a search when a replied card already identifies the exact record.

Acceptance requirements

- A reply to a planning card updates that exact record.
- A reply to a memory card can append context or correct the memory.
- Time-bounded searches use explicit timezone-aware date ranges.
- The dashboard and API-call inspector show reply and card context clearly.

### Phase 5.8

Planning dashboard and local settings experience

Status complete

- Replace the four-panel planning page with Places, Saved ideas, Events, and Reminders tabs.
- Add search, filters, add controls, edit controls, and record-specific forms.
- Add notes and meaningful occurrence fields where the data model supports them.
- Add confirmed hard deletion only in the dashboard with a two-step confirmation.
- Keep Telegram deletion as the existing card-based user action.
- Add location autocomplete with debounce, keyboard navigation, normalized selection, and timezone resolution.
- Keep manual location input available when no suggestion is selected.
- Show configuration values and active prompt version clearly without exposing secrets.

Acceptance requirements

- Each planning record type has an appropriate add and edit form.
- Destructive dashboard actions require explicit confirmation.
- A selected city updates the stored timezone used by future agent context.
- Planning counts and cards reflect database state immediately after writes.

### Phase 5.9

Observability, attachments, and release hardening

Status complete

- Upgrade the logs page into a bounded live log viewer with levels, timestamps, search, filters, copy, pause, auto-scroll, and line-wrap controls.
- Keep runtime logs bounded and redact secrets, tokens, private URLs, and unnecessary attachment data.
- Improve attachment diagnostics for images, documents, audio, video, oversized files, failed downloads, empty files, and corrupt media.
- Keep temporary attachment files short-lived and remove them after success, failure, timeout, cancellation, or restart.
- Verify attachment guidance in the shared prompt and preview.
- Run end-to-end tests for memory writes, planning writes, updates, card replies, time-aware retrieval, prompt refresh, dashboard consistency, and Telegram command behavior.
- Run the full test suite, lint, formatting, type checks, migration checks, and diff checks.
- Update the README, architecture, build specification, security notes, agent rules, implementation plan, and current release notes.

Acceptance requirements

- Every failed operation has a clear Telegram message and a detailed dashboard log.
- The dashboard shows current database state without requiring a process restart.
- No temporary attachment remains after its retention window.
- The release can be installed and upgraded using the documented procedure.
