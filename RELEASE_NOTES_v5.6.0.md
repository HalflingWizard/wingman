# Wingman 5.6.0

## Simplified agent tools

- Reduced normal model requests to direct memory and planning tools.
- Removed proposal, confirmation, note-only, and action-registration tools from the active agent interface.
- Added one shared `update_planning_item` tool for places, saved ideas, events, and reminders.
- Added ownership checks and clear validation for planning updates and ISO 8601 dates.

## Reliable multi-action work

- Kept the bounded primary-agent tool loop so several safe actions can finish in one request.
- Added per-turn idempotency protection so repeated identical writes do not create duplicates.
- Kept deletion under explicit Telegram card and dashboard controls.

## Compatibility

Legacy persistence helpers remain available for existing data and migrations, but they are not exposed as normal model tools.
