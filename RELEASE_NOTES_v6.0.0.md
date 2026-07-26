# Wingman 6.0.0 consolidated release notes

This note collects the work delivered through phases 5.1 to 5.10. It is the release summary for the version 6 handoff.

## Telegram lists and cards

- Added `/places` and `/events` list commands with paged inline buttons.
- Added matching `/ideas` and `/reminders` list commands.
- Selecting an item opens its full saved record as a Telegram card.
- Card replies carry the selected record into the next agent request.
- Memory and planning cards show verified records and user deletion controls.

## Prompt and context control

- Added editable prompt sections in the dashboard.
- Added a combined prompt preview that uses the same context builder as real agent calls.
- Persisted prompt versions and refreshed the active prompt after saving.
- Kept personal runtime context separate from dynamic saved records.
- Added reply context, card context, attachment diagnostics, and capability information to agent requests.

## Tool and agent orchestration

- Simplified the active tool set around one primary agent.
- Added bounded multi-round tool execution so several requested actions can finish before the reply.
- Added duplicate-write protection and ownership checks.
- Added verified Telegram cards only after successful database writes.
- Kept deletion under user control through Telegram cards and dashboard actions.

## Unified saved-context retrieval

- Added one semantic search tool across memories, places, ideas, events, and reminders.
- Combined embedding similarity, lexical matching, and useful recency signals.
- Added persisted and lazy-created embeddings for planning records.
- Added category selection, list mode, city filters, and time-range filters.
- Added time-aware searches for periods such as last week, last June, and this month.
- Allowed the agent to broaden, refine, or search multiple categories when a request spans them.
- Preserved the complete turn and all earlier tool results during continuation rounds.
- Added retrieval diagnostics with query details, candidate text, score components, and selected records.

## Dashboard improvements

- Added editable context and prompt management.
- Added planning tabs for places, ideas, events, and reminders.
- Added structured cards, edit controls, hard-delete confirmation, and hidden deleted records by default.
- Improved API call, retrieval, JSON, and log viewers with fixed-height scrolling, highlighting, and copy controls.
- Added usage reporting for tokens and estimated cost over time.
- Added runtime revision and update information.
- Improved settings for model, identity, timezone, location, and connection values.

## Attachments and Telegram intake

- Added voice transcription using `gpt-4o-mini-transcribe`.
- Added image, document, and video handling with capability-aware responses.
- Added video transcript and extracted-frame context.
- Added attachment classification for files delivered as documents or other Telegram media types.
- Added batching for captions, albums, long messages, and related updates.
- Added temporary-file cleanup and clearer errors for unsupported, empty, corrupted, failed, or oversized files.

## Reliability and operations

- Added health checks, dependency checks, runtime logs, error diagnostics, and end-to-end test coverage.
- Improved update handling with dependency installation, revision verification, dirty-tree protection, and safe daemon restart.
- Added bounded log retention and clearer Telegram errors when processing or model work fails.
- Added conversation history summaries that preserve recent detail without growing the request forever.
- Kept the application local, owner-scoped, and free of public authentication requirements.

## Location-aware personal context

- Added a separate city or location setting instead of inferring residence from the timezone.
- Added `WINGMAN_LOCATION` to environment configuration.
- Added the location to Settings and the Context page personal context display.
- Included the configured location in the static runtime context used by the agent.
