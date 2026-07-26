# Wingman 5.5.0

## Dashboard-owned agent context

- Replaced the single context editor with organized prompt sections.
- Added editable sections for personality, memory and planning, tool orchestration, attachments, and custom instructions.
- Added read-only owner, primary person, timezone, local time, model, tools, and capability information.
- Added active prompt version metadata with version ID, timestamp, active status, and updater.
- Added a combined final-context preview using the same builders as real model requests.
- Prompt changes are loaded from the active configuration on every new request without restarting Wingman.
