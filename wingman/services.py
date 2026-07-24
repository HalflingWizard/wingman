"""Persistence and validated domain services."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wingman.models import (
    AgentRun,
    Conversation,
    ConversationSummary,
    Memory,
    MemoryNote,
    Message,
    PendingState,
    SummaryUpdate,
    TelegramCard,
    ToolExecution,
    User,
)


def authorized_user(session: Session, owner_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_user_id == owner_id))


def get_or_create_user(session: Session, telegram_user_id: int, name: str = "") -> User:
    user = authorized_user(session, telegram_user_id)
    if user is None:
        user = User(telegram_user_id=telegram_user_id, name=name)
        session.add(user)
        session.flush()
    return user


def get_or_create_conversation(session: Session, user: User) -> Conversation:
    conversation = session.scalar(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at)
    )
    if conversation is None:
        conversation = Conversation(user=user)
        session.add(conversation)
        session.flush()
    return conversation


def add_message(
    session: Session,
    conversation: Conversation,
    sender: str,
    text: str,
    telegram_message_id: int | None = None,
) -> Message:
    message = Message(
        conversation=conversation,
        sender=sender,
        text=text,
        telegram_message_id=telegram_message_id,
    )
    session.add(message)
    session.commit()
    return message


MEMORY_STATUSES = {"confirmed", "observed", "inferred", "uncertain", "corrected", "deleted"}
MEMORY_TYPES = {
    "fact",
    "preference",
    "dislike",
    "interest",
    "observation",
    "inference",
    "communication_preference",
    "sensitivity",
    "promise",
    "gift_clue",
    "style_clue",
    "food_clue",
    "entertainment_clue",
    "relationship_detail",
}


def create_memory(
    session: Session,
    user: User,
    statement: str,
    memory_type: str = "fact",
    status: str = "confirmed",
    confidence: float = 1.0,
    importance: int = 3,
) -> Memory:
    if not statement.strip() or len(statement) > 4000:
        raise ValueError("Memory statement must contain 1 to 4000 characters")
    if memory_type not in MEMORY_TYPES:
        raise ValueError("Unsupported memory type")
    if status not in MEMORY_STATUSES or not 0 <= confidence <= 1 or not 1 <= importance <= 5:
        raise ValueError("Invalid memory fields")
    memory = Memory(
        user_id=user.id,
        statement=statement.strip(),
        type=memory_type,
        status=status,
        confidence=confidence,
        importance=importance,
        embedding_text=statement.strip(),
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory


def get_owned_memory(session: Session, user: User, memory_id: str) -> Memory | None:
    memory = session.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        return None
    return memory


def update_memory(session: Session, user: User, memory_id: str, **fields: Any) -> Memory:
    memory = get_owned_memory(session, user, memory_id)
    if memory is None:
        raise ValueError("Memory does not exist")
    allowed = {"statement", "type", "status", "confidence", "importance"}
    if set(fields) - allowed:
        raise ValueError("Unsupported memory fields")
    if "statement" in fields and (
        not str(fields["statement"]).strip() or len(fields["statement"]) > 4000
    ):
        raise ValueError("Memory statement must contain 1 to 4000 characters")
    if "type" in fields and fields["type"] not in MEMORY_TYPES:
        raise ValueError("Unsupported memory type")
    if "status" in fields and fields["status"] not in MEMORY_STATUSES:
        raise ValueError("Unsupported memory status")
    if "confidence" in fields and not 0 <= float(fields["confidence"]) <= 1:
        raise ValueError("Confidence must be between 0 and 1")
    if "importance" in fields and not 1 <= int(fields["importance"]) <= 5:
        raise ValueError("Importance must be between 1 and 5")
    for key, value in fields.items():
        setattr(memory, key, value.strip() if key == "statement" else value)
    memory.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(memory)
    return memory


def delete_memory(session: Session, user: User, memory_id: str) -> Memory:
    memory = update_memory(session, user, memory_id, status="deleted")
    memory.deleted_at = datetime.now(UTC)
    session.commit()
    session.refresh(memory)
    return memory


def confirm_memory(session: Session, user: User, memory_id: str) -> Memory:
    return update_memory(session, user, memory_id, status="confirmed", confidence=1.0)


def add_memory_note(
    session: Session,
    user: User,
    memory_id: str,
    text: str,
    note_type: str = "evidence",
    confidence: float | None = None,
) -> MemoryNote:
    memory = get_owned_memory(session, user, memory_id)
    if memory is None or memory.status == "deleted":
        raise ValueError("Memory does not exist")
    if not text.strip() or len(text) > 2000:
        raise ValueError("Memory note must contain 1 to 2000 characters")
    if note_type not in {"evidence", "context", "correction", "source", "interpretation"}:
        raise ValueError("Unsupported memory note type")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("Confidence must be between 0 and 1")
    note = MemoryNote(
        memory_id=memory.id,
        text=text.strip(),
        note_type=note_type,
        confidence=confidence,
    )
    session.add(note)
    memory.embedding_text = f"{memory.statement}. {text.strip()}"
    memory.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(note)
    return note


def list_memory_notes(session: Session, user: User, memory_id: str) -> list[MemoryNote]:
    if get_owned_memory(session, user, memory_id) is None:
        raise ValueError("Memory does not exist")
    return list(
        session.scalars(
            select(MemoryNote)
            .where(MemoryNote.memory_id == memory_id)
            .order_by(MemoryNote.created_at)
        )
    )


def update_memory_note(
    session: Session,
    user: User,
    note_id: str,
    text: str,
    note_type: str = "evidence",
) -> MemoryNote:
    note = session.get(MemoryNote, note_id)
    if note is None:
        raise ValueError("Memory note does not exist")
    memory = get_owned_memory(session, user, note.memory_id)
    if memory is None:
        raise ValueError("Memory does not exist")
    if not text.strip() or len(text) > 2000:
        raise ValueError("Memory note must contain 1 to 2000 characters")
    if note_type not in {"evidence", "context", "correction", "source", "interpretation"}:
        raise ValueError("Unsupported memory note type")
    note.text = text.strip()
    note.note_type = note_type
    memory.embedding_text = f"{memory.statement}. {note.text}"
    memory.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(note)
    return note


def delete_memory_note(session: Session, user: User, note_id: str) -> None:
    note = session.get(MemoryNote, note_id)
    if note is None or get_owned_memory(session, user, note.memory_id) is None:
        raise ValueError("Memory note does not exist")
    session.delete(note)
    session.commit()


def set_memory_embedding(
    session: Session, user: User, memory_id: str, vector: list[float]
) -> Memory:
    memory = get_owned_memory(session, user, memory_id)
    if memory is None:
        raise ValueError("Memory does not exist")
    memory.embedding_json = json.dumps(vector)
    session.commit()
    session.refresh(memory)
    return memory


def list_memories(session: Session, user: User, include_deleted: bool = False) -> list[Memory]:
    query = select(Memory).where(Memory.user_id == user.id).order_by(Memory.updated_at.desc())
    if not include_deleted:
        query = query.where(Memory.status != "deleted")
    return list(session.scalars(query))


def create_agent_run(
    session: Session,
    conversation: Conversation,
    model_name: str,
    request_snapshot: str | None = None,
) -> AgentRun:
    run = AgentRun(
        conversation_id=conversation.id,
        model_name=model_name,
        request_snapshot=request_snapshot,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_agent_run(
    session: Session,
    run_id: str,
    status: str,
    latency_ms: int | None = None,
    error: str | None = None,
    response_snapshot: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise ValueError("Agent run does not exist")
    run.status = status
    run.latency_ms = latency_ms
    run.error = error
    run.response_snapshot = response_snapshot
    run.input_tokens = input_tokens
    run.output_tokens = output_tokens
    run.completed_at = datetime.now(UTC)
    session.commit()


def get_or_create_summary(session: Session, conversation: Conversation) -> ConversationSummary:
    summary = session.scalar(
        select(ConversationSummary).where(ConversationSummary.conversation_id == conversation.id)
    )
    if summary is None:
        summary = ConversationSummary(conversation_id=conversation.id)
        session.add(summary)
        session.commit()
        session.refresh(summary)
    return summary


def save_summary(
    session: Session,
    conversation: Conversation,
    summary_text: str,
    message_ids: list[str],
    through_message_id: str | None,
) -> ConversationSummary:
    summary = get_or_create_summary(session, conversation)
    previous_text = summary.summary_text
    summary.summary_text = summary_text.strip()
    summary.estimated_tokens = max(1, len(summary.summary_text) // 4)
    summary.summarized_through_message_id = through_message_id
    summary.updated_at = datetime.now(UTC)
    session.add(
        SummaryUpdate(
            summary_id=summary.id,
            previous_text=previous_text,
            added_message_ids_json=json.dumps(message_ids),
            new_text=summary.summary_text,
        )
    )
    session.commit()
    session.refresh(summary)
    return summary


def get_open_pending_state(
    session: Session, user: User, conversation: Conversation
) -> PendingState | None:
    now = datetime.now(UTC)
    state = session.scalar(
        select(PendingState)
        .where(
            PendingState.user_id == user.id,
            PendingState.conversation_id == conversation.id,
            PendingState.status == "open",
        )
        .order_by(PendingState.created_at.desc())
    )
    if state is not None and state.expires_at.replace(tzinfo=UTC) <= now:
        state.status = "expired"
        session.commit()
        return None
    return state


def create_pending_state(
    session: Session,
    user: User,
    conversation: Conversation,
    state_type: str,
    missing_information: str,
    question_asked: str,
    expires_at: datetime,
    related_entity_id: str | None = None,
) -> PendingState:
    state = PendingState(
        user_id=user.id,
        conversation_id=conversation.id,
        state_type=state_type,
        missing_information=missing_information,
        question_asked=question_asked,
        expires_at=expires_at,
        related_entity_id=related_entity_id,
    )
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def record_tool_execution(
    session: Session,
    user: User,
    tool_name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any] | None = None,
    status: str = "completed",
    error: str | None = None,
    agent_run_id: str | None = None,
) -> ToolExecution:
    execution = ToolExecution(
        agent_run_id=agent_run_id,
        user_id=user.id,
        tool_name=tool_name,
        status=status,
        input_json=json.dumps(input_data, sort_keys=True),
        output_json=json.dumps(output_data, sort_keys=True) if output_data else None,
        error=error,
    )
    session.add(execution)
    session.commit()
    return execution


def save_telegram_card(
    session: Session,
    memory: Memory,
    chat_id: int,
    message_id: int,
) -> TelegramCard:
    card = session.scalar(select(TelegramCard).where(TelegramCard.memory_id == memory.id))
    if card is None:
        card = TelegramCard(
            memory_id=memory.id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
        )
        session.add(card)
    else:
        card.telegram_chat_id = chat_id
        card.telegram_message_id = message_id
        card.status = "synced"
        card.updated_at = datetime.now(UTC)
    memory.telegram_card_message_id = message_id
    session.commit()
    return card


def mark_card_deleted(session: Session, memory_id: str) -> None:
    card = session.scalar(select(TelegramCard).where(TelegramCard.memory_id == memory_id))
    if card is not None:
        card.status = "deleted"
        card.updated_at = datetime.now(UTC)
        session.commit()


def pending_deleted_cards(session: Session, user: User, chat_id: int) -> list[TelegramCard]:
    return list(
        session.scalars(
            select(TelegramCard)
            .join(Memory, Memory.id == TelegramCard.memory_id)
            .where(
                Memory.user_id == user.id,
                TelegramCard.telegram_chat_id == chat_id,
                TelegramCard.status == "deleted",
            )
        )
    )


def mark_card_cleaned(session: Session, card_id: str) -> None:
    card = session.get(TelegramCard, card_id)
    if card is not None:
        card.status = "cleaned"
        card.updated_at = datetime.now(UTC)
        session.commit()
