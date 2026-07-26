# Wingman 5.7.0

## Time-aware search

- Memory searches accept date ranges, memory types, and person context.
- Planning searches accept item types, cities, and date ranges.
- Common periods such as yesterday, last week, last month, and this month use the configured timezone.
- Search uses meaningful dates for each record type, including memory creation, event start, and reminder schedule times.

## Telegram reply context

- Replies to bot messages now include the previous message in the agent context.
- Replies to saved cards include the exact owned record and its current fields.
- The model can update the referenced memory or planning record without exposing internal IDs.
- Planning list selections now preserve structured record context for the next turn.
