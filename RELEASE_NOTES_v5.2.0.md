# Wingman 5.2.0

Version 5.2 improves Telegram planning navigation and makes explicit memory retrieval requests more reliable.

## Highlights

- Added `/ideas` and `/reminders` commands.
- Added paginated menus for places, ideas, events, and reminders.
- Added stronger tool behavior when the owner explicitly asks Wingman to use saved memories.

## Planning selectors

- All four planning lists now use five-item paginated menus.
- Place, idea, event, and reminder buttons use distinct icons and show only titles.
- Selecting an item opens its complete detail card with the existing delete control.
- A verified selection is recorded as a user-context message, so the next model request and dashboard conversation show which item the owner selected.

## Retrieval behavior

- Automatic tool choice remains enabled during ordinary conversation.
- Requests such as “use my saved memories” or “what do you remember about Chloe?” trigger an initial memory search.
- After the required search, tool selection returns to automatic mode so the model can continue with other tools.
- Added tests for explicit retrieval requests and planning list behavior.

## Validation

- 66 automated tests passed.
- Ruff, formatting, mypy, and diff checks passed.
