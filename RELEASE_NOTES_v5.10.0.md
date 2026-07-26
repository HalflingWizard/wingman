# Wingman 5.10.0

## Reliable saved-context retrieval

- Added one unified semantic search across personal memories, places, saved ideas, events, and reminders.
- Required the first agent step to make an explicit retrieval decision without preloading saved records into the prompt.
- Let the model choose relevant categories, semantic queries, date and city filters, and ranked search or list behavior.
- Added repeated and cross-category searches inside the existing bounded tool loop.

## Search quality

- Added hybrid cosine similarity, normalized lexical overlap, and recency ranking for every saved category.
- Added embeddings for places, ideas, events, and reminders.
- Added lazy embedding generation for existing records and records created through the dashboard.
- Kept lexical retrieval available when embedding generation fails.
- Added relevance thresholds so unrelated records are not inserted into responses.

## Agent loop and diagnostics

- Preserved the original user request and every prior tool result across all Responses API tool rounds.
- Added validation for the required initial retrieval step.
- Expanded retrieval diagnostics with selected categories, search mode, candidate text, score components, selected records, and failures.
- Kept internal record IDs, scores, and database mechanics out of normal Telegram replies.

## Validation

- Added direct and indirect place recommendation tests.
- Added person, idea, event, reminder, cross-category, no-match, list, update, ambiguity, lazy embedding, grounding, and multi-round refinement tests.
- Completed the full lint, formatting, type-checking, and test suite.
