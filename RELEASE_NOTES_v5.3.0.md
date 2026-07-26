# Wingman 5.3.0

## Mandatory memory retrieval

- Wingman now performs one `search_memories` call before every model response when tools are available.
- The search query is generated from the current request and its relevant people or subjects.
- Empty results do not block the response. Wingman continues with the conversation and general knowledge.
- Other tools remain automatic, and the model can continue using them after the memory search.
- Added tests for mandatory retrieval and automatic follow-up tool selection.
