# Wingman agent guide

This file is for coding agents working in Wingman. Read it before changing code.

## Project shape

Wingman is a local Python application for one authorized Telegram owner.

| Area | Location |
| --- | --- |
| Telegram polling and media intake | `wingman/telegram_bot.py` |
| OpenAI Responses API and tools | `wingman/model_client.py`, `wingman/tools.py` |
| Context and retrieval | `wingman/context_builder.py`, `wingman/retrieval.py` |
| Persistence services | `wingman/services.py`, `wingman/models.py` |
| Dashboard | `wingman/web.py` |
| Runtime settings | `wingman/config.py`, `.env.example` |
| User-editable prompt | `prompts/wingman.md` |
| Tests | `tests/` |
| Deployment | `deploy/wingman.service`, `scripts/` |

Keep the application local, owner-scoped, and simple. Do not add public authentication, remote storage, or unrelated infrastructure without an explicit request.

## Development workflow

1. Read `BUILD_SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, and the relevant source files before coding.
2. Turn the request into observable acceptance criteria.
3. Add the work to the current phase in `IMPLEMENTATION_PLAN.md` before implementation.
4. Make surgical changes. Preserve unrelated user changes in the working tree.
5. Add mocked tests for external APIs and regression tests for user-visible behavior.
6. Run the quality gates from the repository root.

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy wingman
.venv/bin/pytest
```

Do not require live Telegram or OpenAI credentials for tests. If a change sends an OpenAI request in a test or script, estimate its cost first and warn the owner if the estimate could exceed 25 dollars.

## Version and phase policy

The current release is 4.3.0. Every implemented phase increments the release version.

| Phase | Version |
| --- | --- |
| 4.1 | 4.1.0 |
| 4.2 | 4.2.0 |
| 4.3 | 4.3.0 |

Update the version in `pyproject.toml` and `wingman/__init__.py`. Update the README, architecture notes, security notes, implementation plan, and configuration documentation when the change affects them. Create release notes for the current release. After release notes have been used, remove obsolete release-note files. Keep only the current release notes unless the owner asks to retain an older release.

Do not call a phase complete until its tests pass and its acceptance criteria are documented. Do not silently combine unrelated phases.

## Conversation and memory behavior

- Natural conversation is the primary product requirement.
- Do not expose tool names, scores, IDs, database operations, or retrieval mechanics in normal replies.
- Keep facts, observations, and inferences separate.
- Save explicit durable details when the owner asks to remember them.
- Use duplicate-aware search before creating a memory.
- Use notes or updates for existing records instead of duplicates.
- Allow multiple valid actions from one message. Do not stop after the first successful tool call.
- Planning records may be partial. Unknown optional fields must remain unknown rather than blocking useful capture.
- Telegram cards must represent verified database records. Never show a success card for an unverified write.
- Temporary media files must be deleted after processing or failure.

## API tools and schemas

Tool descriptions and JSON schemas are part of the behavior. Use clear descriptions, exact allowed values, required fields, and examples of valid values where an enum-like field is used. Keep tool execution validated, audited, bounded, and ownership-checked.

When a tool action fails, preserve the failure in diagnostics and return a natural user-facing response. Do not claim that an operation succeeded unless the database write was verified.

## Dashboard design

The dashboard is server-rendered in `wingman/web.py` and should remain usable without a build step.

- Keep a readable maximum content width and prevent horizontal page scrolling.
- Use the existing minimal visual style and Font Awesome icons consistently.
- Prefer clear cards, grouped panels, useful spacing, and obvious primary actions.
- Long JSON, logs, prompts, summaries, and diagnostics use fixed-height scrollable code blocks.
- Highlight JSON and provide copy buttons where raw data is shown.
- Keep secrets masked and avoid displaying private credentials in diagnostics.
- Live pages should use no-cache behavior when stale data would mislead the owner.
- Health should show actionable dependencies and checks, not duplicate repository information already shown elsewhere.

## Telegram intake and status

Telegram may deliver albums, captions, long text, and media as separate updates. Preserve the batching and quiet-period behavior when changing intake. Test text, voice, image, document, video, circular video, captions, and multiple attachments.

The owner-facing flow should show typing while model work is in progress. Do not add transient status stickers unless the owner brings that phase back into scope.

## Updates and deployment

The safe updater must refuse to overwrite a dirty Git worktree. It must install Python dependencies, verify the loaded revision, check media dependencies, and restart safely under systemd without creating a second Telegram poller.

When changing update behavior, inspect `deploy/wingman.service` and document any required `systemctl` commands. Never tell the owner to discard local changes without showing how to inspect them first.

## Documentation style

Write for an international undergraduate reader. Be direct and concise. Prefer short sections and practical examples. Do not write a long historical essay in the README. Describe what Wingman is, what it can do, how to install it, how to run it, and where to find current release notes.

## Do not do these things

- Do not use personal names or private relationship details in defaults, examples, fixtures, or documentation.
- Do not add a live API call merely to validate ordinary code.
- Do not delete user data, reset Git, or discard local changes without explicit authorization.
- Do not broaden the task into external integrations or public deployment.
- Do not add a runtime self-review loop that can bypass application validation or human control.
