"""Small deterministic hybrid retrieval for memories."""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from wingman.models import Conversation, Memory, MemoryNote, User
from wingman.services import list_memories
from wingman.time_ranges import within_range

WORD_RE = re.compile(r"[a-z0-9']+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "do",
    "does",
    "for",
    "how",
    "i",
    "is",
    "kind",
    "of",
    "she",
    "should",
    "the",
    "they",
    "to",
    "type",
    "what",
    "which",
    "would",
}
TERM_ALIASES = {
    "accessories": "accessory",
    "accessory": "accessory",
    "jewellery": "accessory",
    "jewelry": "accessory",
}
MIN_KEYWORD_MATCH = 0.5
MIN_SEMANTIC_SIMILARITY = 0.45


@dataclass(frozen=True)
class RetrievalResult:
    memory: Memory
    score: float
    semantic_similarity: float
    keyword_match: float
    importance: float
    confidence: float
    recency: float
    notes: tuple[MemoryNote, ...] = ()


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> set[str]:
    words = set()
    for raw_word in WORD_RE.findall(text.lower()):
        if raw_word in STOP_WORDS:
            continue
        word = _stem(raw_word)
        words.add(TERM_ALIASES.get(word, word))
    return words


def cosine_similarity(left: list[float], right: list[float]) -> float:
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
        return cosine_similarity(json.loads(memory.embedding_json), query_vector)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def retrieve_memories(
    session: Session,
    user: User,
    query: str,
    limit: int = 8,
    query_vector: list[float] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[RetrievalResult]:
    query_words = tokenize(query)
    results: list[RetrievalResult] = []
    now = datetime.now(UTC)
    for memory in list_memories(session, user):
        if not within_range(memory.created_at, date_from, date_to):
            continue
        memory_words = tokenize(f"{memory.statement} {memory.embedding_text or ''}")
        notes = tuple(
            session.scalars(
                select(MemoryNote)
                .where(MemoryNote.memory_id == memory.id)
                .order_by(MemoryNote.created_at)
            )
        )
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
        if keyword_match >= MIN_KEYWORD_MATCH or semantic_similarity >= MIN_SEMANTIC_SIMILARITY:
            results.append(
                RetrievalResult(
                    memory,
                    score,
                    semantic_similarity,
                    keyword_match,
                    importance,
                    memory.confidence,
                    recency,
                    notes,
                )
            )
    results.sort(key=lambda item: (-item.score, -item.memory.updated_at.timestamp()))
    for result in results[:limit]:
        result.memory.last_retrieved_at = now
    session.commit()
    return results[:limit]


def retrieval_query(
    query: str, user: User, filters: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "semantic_query": query,
        "keywords": sorted(tokenize(query)),
        "user_id": user.id,
        "filters": {
            "status": ["confirmed", "observed", "inferred", "uncertain"],
            **(filters or {}),
        },
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
            "memory_text": result.memory.statement,
            "embedding_available": bool(result.memory.embedding_json),
            "score": result.score,
            "semantic_similarity": result.semantic_similarity,
            "keyword_match": result.keyword_match,
            "importance": result.importance,
            "confidence": result.confidence,
            "recency": result.recency,
            "notes": [
                {
                    "note_id": note.id,
                    "text": note.text,
                    "note_type": note.note_type,
                    "source_message_id": note.source_message_id,
                }
                for note in result.notes
            ],
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


def retrieval_context_usage(
    results: list[RetrievalResult],
    answer: str,
    tool_trace: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    answer_words = tokenize(answer)
    retrieved_ids = [result.memory.id for result in results]
    statements = {result.memory.id: result.memory.statement for result in results}
    retrieved_records: list[dict[str, str]] = [
        {"category": "memory", "record_id": result.memory.id} for result in results
    ]
    if tool_trace:
        for trace in tool_trace:
            if trace.get("name") not in {"search_memories", "search_saved_context"}:
                continue
            output = trace.get("output")
            if not isinstance(output, dict) or not output.get("ok"):
                continue
            result = output.get("result")
            if not isinstance(result, dict):
                continue
            records = (
                result.get("memories")
                if trace.get("name") == "search_memories"
                else result.get("records")
            )
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                record_id = record.get("memory_id") or record.get("record_id")
                statement = record.get("statement") or record.get("content") or record.get("title")
                category = str(record.get("category") or "memory")
                if isinstance(record_id, str) and isinstance(statement, str):
                    retrieved_ids.append(record_id)
                    statements[record_id] = statement
                    retrieved_records.append({"category": category, "record_id": record_id})
    retrieved_ids = list(dict.fromkeys(retrieved_ids))
    used_ids = [
        memory_id
        for memory_id in retrieved_ids
        if tokenize(statements.get(memory_id, "")) & answer_words
    ]
    return {
        "retrieved_memory_ids": retrieved_ids,
        "mentioned_memory_ids": used_ids,
        "unmentioned_memory_ids": [item for item in retrieved_ids if item not in used_ids],
        "retrieved_record_ids": retrieved_ids,
        "used_record_ids": used_ids,
        "unused_record_ids": [item for item in retrieved_ids if item not in used_ids],
        "retrieved_records": list(
            {(item["category"], item["record_id"]): item for item in retrieved_records}.values()
        ),
        "method": "model-directed unified semantic retrieval with answer overlap diagnostic",
    }
