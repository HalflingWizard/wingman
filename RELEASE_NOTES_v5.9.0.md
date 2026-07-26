# Wingman 5.9.0

## Observability

- Kept live runtime output bounded to the latest 100 lines.
- Added copy, clear-view, pause, and line-wrap controls to the dashboard log viewer.
- Preserved detailed runtime errors with timestamps, stages, source locations, and tracebacks.
- Continued redaction of secrets and attachment bytes in diagnostics.

## Attachment hardening

- Added startup cleanup for stale temporary Wingman media files left after interrupted processing.
- Preserved cleanup after successful processing, failures, timeouts, and cancellations.
- Added regression tests for safe cleanup that leaves unrelated files untouched.

## Release status

Version 5.9.0 completes the planned 5.x roadmap.
