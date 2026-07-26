# Wingman 4.1.0

Wingman 4.1.0 adds reliable owner commands and clearer failure handling.

## Highlights

- Added `/newchat` to clear conversation messages, summaries, pending questions, and action state while preserving memories and planning records.
- `/remember` now uses the normal tool-enabled path so explicit details can become memories, places, ideas, events, or reminders.
- Added Telegram command descriptions for `/start`, `/newchat`, and `/remember`.
- Added configurable model response timeouts.
- Added clear Telegram errors for media processing, model failures, and model timeouts.
- Added durable runtime error history with timestamps, stages, exception types, source files, line numbers, message IDs, and tracebacks.
- Added the error history section to the dashboard Logs page.
- Kept voice uploads within the provider-safe 25 MB limit while adding explicit response timeout controls.
