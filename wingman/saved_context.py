"""Unified semantic retrieval across all owner-saved context."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from wingman.models import (
    Conversation,
    Event,
    Memory,
    Place,
    Reminder,
    RetrievalLog,
    SavedIdea,
    User,
)
from wingman.retrieval import cosine_similarity, tokenize
from wingman.services import (
    list_events,
    list_memories,
    list_memory_notes,
    list_places,
    list_reminders,
    list_saved_ideas,
    planning_record_text,
)
from wingman.time_ranges import within_range

SavedCategory = Literal["memory", "place", "idea", "event", "reminder"]
SAVED_CATEGORIES: tuple[SavedCategory, ...] = (
    "memory",
    "place",
    "idea",
    "event",
    "reminder",
)
MIN_SEMANTIC_SCORE = 0.32
MIN_LEXICAL_SCORE = 0.2


@dataclass(frozen=True)
class SavedDocument:
    category: SavedCategory
    record_id: str
    title: str
    text: str
    embedding_json: str | None
    occurred_at: datetime
    updated_at: datetime
    fields: dict[str, Any]


@dataclass(frozen=True)
class RankedSavedDocument:
    document: SavedDocument
    score: float
    semantic_similarity: float
    lexical_similarity: float
    recency: float
    selected: bool


def _as_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _memory_document(session: Session, user: User, memory: Memory) -> SavedDocument:
    notes = list_memory_notes(session, user, memory.id)
    text = ". ".join([memory.statement, *(note.text for note in notes)])
    return SavedDocument(
        "memory",
        memory.id,
        memory.statement,
        text,
        memory.embedding_json,
        memory.created_at,
        memory.updated_at,
        {
            "memory_type": memory.type,
            "status": memory.status,
            "importance": memory.importance,
            "notes": [note.text for note in notes],
        },
    )


def saved_documents(
    session: Session,
    user: User,
    categories: list[SavedCategory] | None = None,
) -> list[SavedDocument]:
    """Build the owner-scoped searchable corpus without injecting it into a prompt."""
    selected = set(SAVED_CATEGORIES if categories is None else categories)
    documents: list[SavedDocument] = []
    if "memory" in selected:
        documents.extend(
            _memory_document(session, user, item) for item in list_memories(session, user)
        )
    if "place" in selected:
        documents.extend(
            SavedDocument(
                "place",
                item.id,
                item.name,
                item.embedding_text or planning_record_text(item),
                item.embedding_json,
                item.updated_at,
                item.updated_at,
                {
                    "name": item.name,
                    "address": item.address,
                    "city": item.city,
                    "description": item.description,
                    "place_type": item.place_type,
                    "atmosphere_tags": item.atmosphere_tags,
                    "status": item.status,
                },
            )
            for item in list_places(session, user)
        )
    if "idea" in selected:
        documents.extend(
            SavedDocument(
                "idea",
                item.id,
                item.title,
                item.embedding_text or planning_record_text(item),
                item.embedding_json,
                item.updated_at,
                item.updated_at,
                {
                    "title": item.title,
                    "reason": item.reason,
                    "place_id": item.place_id,
                    "status": item.status,
                    "used": item.used,
                },
            )
            for item in list_saved_ideas(session, user)
        )
    if "event" in selected:
        documents.extend(
            SavedDocument(
                "event",
                item.id,
                item.title,
                item.embedding_text or planning_record_text(item),
                item.embedding_json,
                item.start_at,
                item.updated_at,
                {
                    "title": item.title,
                    "start_at": item.start_at.isoformat(),
                    "end_at": item.end_at.isoformat() if item.end_at else None,
                    "timezone": item.timezone,
                    "description": item.description,
                    "event_type": item.event_type,
                    "place_id": item.place_id,
                    "status": item.status,
                },
            )
            for item in list_events(session, user)
        )
    if "reminder" in selected:
        documents.extend(
            SavedDocument(
                "reminder",
                item.id,
                item.title,
                item.embedding_text or planning_record_text(item),
                item.embedding_json,
                item.scheduled_at,
                item.updated_at,
                {
                    "title": item.title,
                    "scheduled_at": item.scheduled_at.isoformat(),
                    "timezone": item.timezone,
                    "event_id": item.event_id,
                    "status": item.status,
                },
            )
            for item in list_reminders(session, user)
        )
    return documents


def set_saved_document_embedding(
    session: Session,
    user: User,
    category: SavedCategory,
    record_id: str,
    vector: list[float],
) -> None:
    """Persist an embedding on one owned saved record."""
    models = {
        "memory": Memory,
        "place": Place,
        "idea": SavedIdea,
        "event": Event,
        "reminder": Reminder,
    }
    record: Any = session.get(models[category], record_id)
    if record is None or record.user_id != user.id:
        raise ValueError("Saved record does not exist")
    record.embedding_json = json.dumps(vector)
    session.commit()


def _semantic_similarity(document: SavedDocument, query_vector: list[float] | None) -> float:
    if query_vector is None or not document.embedding_json:
        return 0.0
    try:
        vector = json.loads(document.embedding_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0
    return cosine_similarity(vector, query_vector) if isinstance(vector, list) else 0.0


def search_saved_context(
    session: Session,
    user: User,
    query: str,
    categories: list[SavedCategory],
    top_k: int,
    query_vector: list[float] | None = None,
    list_mode: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    city: str | None = None,
) -> tuple[list[RankedSavedDocument], list[RankedSavedDocument]]:
    """Rank relevant saved records and return selected results plus full diagnostics."""
    if not categories:
        return [], []
    query_words = tokenize(query)
    now = datetime.now(UTC)
    ranked: list[RankedSavedDocument] = []
    for document in saved_documents(session, user, categories):
        if not within_range(document.occurred_at, date_from, date_to):
            continue
        if (
            city
            and document.category == "place"
            and city.casefold() not in str(document.fields.get("city", "")).casefold()
        ):
            continue
        document_words = tokenize(document.text)
        overlap = len(query_words & document_words)
        lexical = overlap / max(1, len(query_words))
        semantic = _semantic_similarity(document, query_vector)
        age_days = max(
            0.0,
            (now - _as_aware(document.updated_at).astimezone(UTC)).total_seconds() / 86400,
        )
        recency = 1 / (1 + age_days / 90)
        score = 0.72 * semantic + 0.23 * lexical + 0.05 * recency
        selected = list_mode or semantic >= MIN_SEMANTIC_SCORE or lexical >= MIN_LEXICAL_SCORE
        ranked.append(RankedSavedDocument(document, score, semantic, lexical, recency, selected))
    ranked.sort(
        key=lambda item: (
            -item.selected,
            -item.score,
            -_as_aware(item.document.updated_at).timestamp(),
        )
    )
    return [item for item in ranked if item.selected][:top_k], ranked


def result_payload(result: RankedSavedDocument) -> dict[str, Any]:
    """Return a model-safe record with its internal ID available only for tool use."""
    return {
        "category": result.document.category,
        "record_id": result.document.record_id,
        "title": result.document.title,
        "content": result.document.text,
        "occurred_at": result.document.occurred_at.isoformat(),
        "fields": result.document.fields,
        "relevance": {
            "score": round(result.score, 6),
            "semantic_similarity": round(result.semantic_similarity, 6),
            "lexical_similarity": round(result.lexical_similarity, 6),
        },
    }


def log_saved_context_search(
    session: Session,
    user: User,
    conversation: Conversation | None,
    query: str,
    categories: list[SavedCategory],
    list_mode: bool,
    ranked: list[RankedSavedDocument],
    selected: list[RankedSavedDocument],
    filters: dict[str, Any],
) -> None:
    """Persist enough routing and ranking detail to diagnose retrieval failures."""
    log = RetrievalLog(
        user_id=user.id,
        conversation_id=conversation.id if conversation else None,
        query_text=query,
        query_json=json.dumps(
            {
                "semantic_query": query,
                "categories": categories,
                "mode": "list" if list_mode else "search",
                "keywords": sorted(tokenize(query)),
                "filters": filters,
            },
            sort_keys=True,
        ),
        candidates_json=json.dumps(
            [
                {
                    **result_payload(item),
                    "embedding_available": bool(item.document.embedding_json),
                    "selected": item.selected,
                }
                for item in ranked
            ],
            sort_keys=True,
        ),
        selected_json=json.dumps(
            [
                {
                    "category": item.document.category,
                    "record_id": item.document.record_id,
                }
                for item in selected
            ],
            sort_keys=True,
        ),
    )
    session.add(log)
    session.commit()
