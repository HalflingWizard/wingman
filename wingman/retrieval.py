"""Small deterministic hybrid retrieval for memories."""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from wingman.models import Conversation, Memory, User
from wingman.services import list_memories

WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class RetrievalResult:
    memory: Memory
    score: float
    semantic_similarity: float
    keyword_match: float
    importance: float
    confidence: float
    recency: float


def _words(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, numerator / (left_norm * right_norm))


def _semantic_similarity(memory: Memory, query_vector: list[float] | None) -> float:
    if query_vector is None or not memory.embedding_json:
        return 0.0
    try:
        return _cosine(json.loads(memory.embedding_json), query_vector)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def retrieve_memories(
    session: Session,
    user: User,
    query: str,
    limit: int = 8,
    query_vector: list[float] | None = None,
) -> list[RetrievalResult]:
    query_words = _words(query)
    results: list[RetrievalResult] = []
    now = datetime.now(UTC)
    for memory in list_memories(session, user):
        memory_words = _words(f"{memory.statement} {memory.embedding_text or ''}")
        keyword_match = len(query_words & memory_words) / max(1, len(query_words))
        semantic_similarity = _semantic_similarity(memory, query_vector)
        updated_at = memory.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        age_days = max(0.0, (now - updated_at).total_seconds() / 86400)
        recency = 1 / (1 + age_days / 30)
        importance = memory.importance / 5
        score = (
            0.40 * semantic_similarity
            + 0.20 * keyword_match
            + 0.15 * keyword_match
            + 0.10 * importance
            + 0.10 * memory.confidence
            + 0.05 * recency
        )
        if keyword_match or semantic_similarity or memory.importance >= 4:
            results.append(
                RetrievalResult(
                    memory,
                    score,
                    semantic_similarity,
                    keyword_match,
                    importance,
                    memory.confidence,
                    recency,
                )
            )
    results.sort(key=lambda item: (-item.score, -item.memory.updated_at.timestamp()))
    for result in results[:limit]:
        result.memory.last_retrieved_at = now
    session.commit()
    return results[:limit]


def retrieval_query(query: str, user: User) -> dict[str, object]:
    return {
        "semantic_query": query,
        "keywords": sorted(_words(query)),
        "user_id": user.id,
        "filters": {"status": ["confirmed", "observed", "inferred", "uncertain"]},
    }


def log_retrieval(
    session: Session,
    user: User,
    conversation: Conversation,
    query: dict[str, object],
    results: list[RetrievalResult],
) -> None:
    from wingman.models import RetrievalLog

    candidates = [
        {
            "memory_id": result.memory.id,
            "score": result.score,
            "semantic_similarity": result.semantic_similarity,
            "keyword_match": result.keyword_match,
            "importance": result.importance,
            "confidence": result.confidence,
            "recency": result.recency,
        }
        for result in results
    ]
    log = RetrievalLog(
        user_id=user.id,
        conversation_id=conversation.id,
        query_text=str(query["semantic_query"]),
        query_json=json.dumps(query, sort_keys=True),
        candidates_json=json.dumps(candidates, sort_keys=True),
        selected_json=json.dumps([item["memory_id"] for item in candidates], sort_keys=True),
    )
    session.add(log)
    session.commit()
