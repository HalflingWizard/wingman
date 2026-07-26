# Wingman 5.4.0

## Hybrid memory retrieval

- Memory search now embeds the model's query and compares it with stored memory embeddings using cosine similarity.
- Keyword overlap remains part of the ranking so exact terms and related word forms still work.
- Importance, confidence, and recency continue to affect ranking.
- Relevance thresholds reject memories that match only on a shared person's name.
- Lexical fallback remains available when an embedding is missing or the embedding request fails.
- Retrieval diagnostics include semantic similarity, keyword overlap, and other score components.
- Normal tool selection remains automatic. Memory search is no longer forced on every request.
