"""Persistence and validated domain services."""

import json
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wingman.models import (
    ActionGroup,
    ActionItem,
    AgentRun,
    Conversation,
    ConversationSummary,
    Event,
    Memory,
    MemoryNote,
    Message,
    MessageAttachment,
    PendingState,
    Place,
    Reminder,
    RuntimeErrorLog,
    SavedIdea,
    SummaryUpdate,
    TelegramCard,
    TelegramPlanningCard,
    ToolExecution,
    User,
)
from wingman.runtime_log import record_runtime_output


def authorized_user(session: Session, owner_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_user_id == owner_id))


def get_or_create_user(session: Session, telegram_user_id: int, name: str = "") -> User:
    user = authorized_user(session, telegram_user_id)
    if user is None:
        user = User(telegram_user_id=telegram_user_id, name=name)
        session.add(user)
        session.flush()
    elif name and user.name != name:
        user.name = name
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


def save_message_attachments(
    session: Session, message_id: str, attachments: tuple[Any, ...]
) -> list[MessageAttachment]:
    records = [
        MessageAttachment(
            message_id=message_id,
            source_type=attachment.source_type,
            provider_file_id=attachment.provider_file_id,
            filename=attachment.filename or "",
            content_type=attachment.content_type or "",
            size_bytes=attachment.size_bytes,
            width=attachment.width,
            height=attachment.height,
            estimated_characters=attachment.estimated_characters,
            page_count=attachment.page_count,
            expires_at=attachment.expires_at,
            processing_status="processed",
            processed_at=datetime.now(UTC),
        )
        for attachment in attachments
    ]
    session.add_all(records)
    session.commit()
    return records


def message_display_text(session: Session, message: Message) -> str:
    """Return a readable conversation representation including media placeholders."""
    attachments = list(
        session.scalars(select(MessageAttachment).where(MessageAttachment.message_id == message.id))
    )
    counts = {"photo": 0, "document": 0, "voice": 0, "video": 0}
    for attachment in attachments:
        source = attachment.source_type
        if source == "telegram_voice":
            counts["voice"] += 1
        elif source in {"telegram_video", "telegram_video_frame"}:
            counts["video"] += 1
        elif source == "telegram_image" or attachment.content_type.startswith("image/"):
            counts["photo"] += 1
        elif source == "telegram_document":
            counts["document"] += 1
    labels = []
    for key, label in (
        ("photo", "photo"),
        ("document", "document"),
        ("voice", "voice message"),
        ("video", "video"),
    ):
        count = counts[key]
        if count:
            labels.append(f"{count} {label}{'' if count == 1 else 's'}")
    prefix = f"[{', '.join(labels)}]" if labels else ""
    text = message.text.strip()
    return f"{prefix}\n{text}".strip() if prefix and text else prefix or text


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
    source_message_id: str | None = None,
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
        source_message_id=source_message_id,
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


PLACE_STATUSES = {"candidate", "saved", "visited", "dismissed", "deleted"}
EVENT_STATUSES = {"planned", "completed", "cancelled"}
REMINDER_STATUSES = {"scheduled", "completed", "cancelled"}


def _owned(session: Session, model: type[Any], user: User, record_id: str) -> Any:
    record = session.get(model, record_id)
    if record is None or record.user_id != user.id:
        raise ValueError("Record does not exist")
    return record


def create_place(
    session: Session,
    user: User,
    name: str,
    address: str = "",
    city: str = "",
    description: str = "",
    place_type: str = "place",
    status: str = "candidate",
    source_url: str = "",
    atmosphere_tags: str = "",
) -> Place:
    if not name.strip() or len(name) > 200 or status not in PLACE_STATUSES:
        raise ValueError("Invalid place")
    place = Place(
        user_id=user.id,
        name=name.strip(),
        address=address.strip(),
        city=city.strip(),
        description=description.strip(),
        place_type=place_type.strip() or "place",
        status=status,
        source_url=source_url.strip(),
        atmosphere_tags=atmosphere_tags.strip(),
    )
    session.add(place)
    session.commit()
    session.refresh(place)
    return place


def list_places(session: Session, user: User, include_deleted: bool = False) -> list[Place]:
    query = select(Place).where(Place.user_id == user.id).order_by(Place.updated_at.desc())
    if not include_deleted:
        query = query.where(Place.status != "deleted")
    return list(session.scalars(query))


def find_place_by_name(session: Session, user: User, name: str) -> Place | None:
    normalized = name.strip().casefold()
    return next(
        (place for place in list_places(session, user) if place.name.casefold() == normalized),
        None,
    )


def update_place(session: Session, user: User, place_id: str, **fields: Any) -> Place:
    place = session.get(Place, place_id)
    if place is None or place.user_id != user.id:
        raise ValueError("Record does not exist")
    allowed = {
        "name",
        "address",
        "city",
        "description",
        "place_type",
        "status",
        "source_url",
        "atmosphere_tags",
    }
    if set(fields) - allowed or fields.get("status", place.status) not in PLACE_STATUSES:
        raise ValueError("Invalid place fields")
    for key, value in fields.items():
        setattr(place, key, value.strip() if isinstance(value, str) else value)
    place.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(place)
    return place


def create_saved_idea(
    session: Session,
    user: User,
    title: str,
    reason: str = "",
    place_id: str | None = None,
) -> SavedIdea:
    if not title.strip() or len(title) > 200:
        raise ValueError("Invalid saved idea")
    if place_id is not None:
        _owned(session, Place, user, place_id)
    idea = SavedIdea(user_id=user.id, title=title.strip(), reason=reason.strip(), place_id=place_id)
    session.add(idea)
    session.commit()
    session.refresh(idea)
    return idea


def update_saved_idea(session: Session, user: User, idea_id: str, **fields: Any) -> SavedIdea:
    idea = session.get(SavedIdea, idea_id)
    if idea is None or idea.user_id != user.id:
        raise ValueError("Record does not exist")
    allowed = {"title", "reason", "place_id", "status", "used"}
    if set(fields) - allowed:
        raise ValueError("Invalid saved idea fields")
    if "title" in fields and (not str(fields["title"]).strip() or len(fields["title"]) > 200):
        raise ValueError("Invalid saved idea title")
    if fields.get("status", idea.status) == "deleted":
        raise ValueError("Planning deletion is controlled by the owner")
    if "place_id" in fields and fields["place_id"] is not None:
        _owned(session, Place, user, str(fields["place_id"]))
    for key, value in fields.items():
        setattr(idea, key, value.strip() if isinstance(value, str) else value)
    idea.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(idea)
    return idea


def list_saved_ideas(
    session: Session, user: User, include_deleted: bool = False
) -> list[SavedIdea]:
    query = (
        select(SavedIdea).where(SavedIdea.user_id == user.id).order_by(SavedIdea.updated_at.desc())
    )
    if not include_deleted:
        query = query.where(SavedIdea.status != "deleted")
    return list(session.scalars(query))


def find_saved_idea_by_title(session: Session, user: User, title: str) -> SavedIdea | None:
    normalized = title.strip().casefold()
    return next(
        (idea for idea in list_saved_ideas(session, user) if idea.title.casefold() == normalized),
        None,
    )


def create_event(
    session: Session,
    user: User,
    title: str,
    start_at: datetime,
    event_type: str = "event",
    timezone: str = "UTC",
    description: str = "",
    place_id: str | None = None,
) -> Event:
    if not title.strip() or len(title) > 200:
        raise ValueError("Invalid event")
    if place_id is not None:
        _owned(session, Place, user, place_id)
    event = Event(
        user_id=user.id,
        title=title.strip(),
        start_at=start_at,
        event_type=event_type.strip() or "event",
        timezone=timezone.strip() or "UTC",
        description=description.strip(),
        place_id=place_id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def update_event(session: Session, user: User, event_id: str, **fields: Any) -> Event:
    event = session.get(Event, event_id)
    if event is None or event.user_id != user.id:
        raise ValueError("Record does not exist")
    allowed = {
        "title",
        "event_type",
        "start_at",
        "end_at",
        "timezone",
        "status",
        "description",
        "emotional_context",
        "discussed",
        "place_id",
    }
    if set(fields) - allowed or fields.get("status", event.status) not in EVENT_STATUSES:
        raise ValueError("Invalid event fields")
    if "title" in fields and (not str(fields["title"]).strip() or len(fields["title"]) > 200):
        raise ValueError("Invalid event title")
    if "place_id" in fields and fields["place_id"] is not None:
        _owned(session, Place, user, str(fields["place_id"]))
    for key, value in fields.items():
        setattr(event, key, value.strip() if isinstance(value, str) else value)
    event.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(event)
    return event


def list_events(
    session: Session,
    user: User,
    upcoming_only: bool = False,
    include_deleted: bool = False,
) -> list[Event]:
    query = select(Event).where(Event.user_id == user.id).order_by(Event.start_at)
    if upcoming_only:
        query = query.where(Event.status == "planned", Event.start_at >= datetime.now(UTC))
    elif not include_deleted:
        query = query.where(Event.status != "cancelled")
    return list(session.scalars(query))


def find_event(session: Session, user: User, title: str, start_at: datetime) -> Event | None:
    normalized = title.strip().casefold()
    return next(
        (
            event
            for event in list_events(session, user)
            if event.title.casefold() == normalized and _as_utc(event.start_at) == _as_utc(start_at)
        ),
        None,
    )


def create_reminder(
    session: Session,
    user: User,
    title: str,
    scheduled_at: datetime,
    timezone: str = "UTC",
    event_id: str | None = None,
) -> Reminder:
    if not title.strip() or len(title) > 200:
        raise ValueError("Invalid reminder")
    if event_id is not None:
        _owned(session, Event, user, event_id)
    reminder = Reminder(
        user_id=user.id,
        title=title.strip(),
        scheduled_at=scheduled_at,
        timezone=timezone.strip() or "UTC",
        event_id=event_id,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def update_reminder(session: Session, user: User, reminder_id: str, **fields: Any) -> Reminder:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise ValueError("Record does not exist")
    allowed = {"title", "scheduled_at", "timezone", "status", "event_id"}
    if set(fields) - allowed or fields.get("status", reminder.status) not in REMINDER_STATUSES:
        raise ValueError("Invalid reminder fields")
    if "title" in fields and (not str(fields["title"]).strip() or len(fields["title"]) > 200):
        raise ValueError("Invalid reminder title")
    if "event_id" in fields and fields["event_id"] is not None:
        _owned(session, Event, user, str(fields["event_id"]))
    for key, value in fields.items():
        setattr(reminder, key, value.strip() if isinstance(value, str) else value)
    reminder.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(reminder)
    return reminder


def list_reminders(
    session: Session,
    user: User,
    active_only: bool = False,
    include_deleted: bool = False,
) -> list[Reminder]:
    query = select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.scheduled_at)
    if active_only:
        query = query.where(Reminder.status == "scheduled")
    elif not include_deleted:
        query = query.where(Reminder.status != "cancelled")
    return list(session.scalars(query))


def find_reminder(
    session: Session, user: User, title: str, scheduled_at: datetime
) -> Reminder | None:
    normalized = title.strip().casefold()
    return next(
        (
            reminder
            for reminder in list_reminders(session, user)
            if reminder.title.casefold() == normalized
            and _as_utc(reminder.scheduled_at) == _as_utc(scheduled_at)
        ),
        None,
    )


def mark_reminder_delivered(session: Session, reminder_id: str) -> Reminder:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise ValueError("Reminder does not exist")
    reminder.status = "completed"
    reminder.delivery_status = "sent"
    reminder.last_triggered_at = datetime.now(UTC)
    reminder.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(reminder)
    return reminder


def planning_context(
    session: Session, user: User
) -> tuple[list[Place], list[SavedIdea], list[Event], list[Reminder]]:
    now = datetime.now(UTC)
    horizon = now + timedelta(days=90)
    places = [
        place for place in list_places(session, user) if place.status in {"candidate", "saved"}
    ]
    ideas = [idea for idea in list_saved_ideas(session, user) if not idea.used]
    events = [
        event
        for event in list_events(session, user)
        if event.status == "planned"
        and _as_utc(event.start_at) >= now
        and _as_utc(event.start_at) <= horizon
    ]
    reminders = [
        reminder
        for reminder in list_reminders(session, user, active_only=True)
        if _as_utc(reminder.scheduled_at) >= now and _as_utc(reminder.scheduled_at) <= horizon
    ]
    return places[:10], ideas[:10], events[:10], reminders[:10]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
    request_snapshot: str | None = None,
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
    if request_snapshot is not None:
        run.request_snapshot = request_snapshot
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


ACTION_TERMINAL_STATUSES = {
    "completed",
    "duplicate",
    "needs_clarification",
    "failed",
    "dismissed",
    "blocked",
}


def create_action_group(
    session: Session,
    user: User,
    conversation: Conversation,
    source_message_id: str | None = None,
) -> ActionGroup:
    group = ActionGroup(
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source_message_id,
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def register_action_items(
    session: Session,
    user: User,
    group: ActionGroup,
    actions: list[dict[str, Any]],
) -> list[ActionItem]:
    existing = {
        item.action_key: item
        for item in session.scalars(select(ActionItem).where(ActionItem.group_id == group.id))
    }
    records: list[ActionItem] = []
    for action in actions:
        key = str(action["action_id"]).strip()
        if not key or key in existing:
            continue
        record = ActionItem(
            group_id=group.id,
            user_id=user.id,
            action_key=key,
            action_type=str(action.get("action_type", "memory")),
            statement=str(action.get("statement", "")).strip(),
            requires_confirmation=bool(action.get("requires_confirmation", False)),
            status=("awaiting_confirmation" if action.get("requires_confirmation") else "pending"),
        )
        session.add(record)
        records.append(record)
    group.updated_at = datetime.now(UTC)
    session.commit()
    for record in records:
        session.refresh(record)
    return records


def get_open_action_group(
    session: Session, user: User, conversation: Conversation
) -> ActionGroup | None:
    return session.scalar(
        select(ActionGroup)
        .where(
            ActionGroup.user_id == user.id,
            ActionGroup.conversation_id == conversation.id,
            ActionGroup.status == "open",
        )
        .order_by(ActionGroup.updated_at.desc())
    )


def action_ledger(session: Session, user: User, conversation: Conversation) -> dict[str, Any]:
    group = get_open_action_group(session, user, conversation)
    if group is None:
        return {"group_id": None, "items": [], "continue_required": False}
    items = list(
        session.scalars(
            select(ActionItem)
            .where(ActionItem.group_id == group.id, ActionItem.user_id == user.id)
            .order_by(ActionItem.created_at)
        )
    )
    return {
        "group_id": group.id,
        "items": [
            {
                "action_id": item.action_key,
                "action_type": item.action_type,
                "statement": item.statement,
                "requires_confirmation": item.requires_confirmation,
                "status": item.status,
                "result": json.loads(item.result_json) if item.result_json else None,
                "error": item.error,
            }
            for item in items
        ],
        "continue_required": any(item.status == "pending" for item in items),
    }


def mark_action_item(
    session: Session,
    user: User,
    action_key: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> ActionItem | None:
    item = session.scalar(
        select(ActionItem).where(
            ActionItem.user_id == user.id,
            ActionItem.action_key == action_key,
            ActionItem.status.not_in(ACTION_TERMINAL_STATUSES),
        )
    )
    if item is None:
        return None
    item.status = status
    item.result_json = json.dumps(result, sort_keys=True) if result is not None else None
    item.error = error
    item.updated_at = datetime.now(UTC)
    group = session.get(ActionGroup, item.group_id)
    session.flush()
    if group is not None:
        remaining = session.scalar(
            select(ActionItem.id).where(
                ActionItem.group_id == group.id,
                ~ActionItem.status.in_(ACTION_TERMINAL_STATUSES),
            )
        )
        if remaining is None:
            group.status = "completed"
        group.updated_at = datetime.now(UTC)
    session.commit()
    return item


def confirm_action_items(
    session: Session, user: User, conversation: Conversation, action_keys: list[str]
) -> dict[str, Any]:
    group = get_open_action_group(session, user, conversation)
    if group is None:
        return {"confirmed": [], "missing": action_keys}
    query = select(ActionItem).where(
        ActionItem.group_id == group.id,
        ActionItem.user_id == user.id,
        ActionItem.status == "awaiting_confirmation",
    )
    if action_keys:
        query = query.where(ActionItem.action_key.in_(action_keys))
    items = list(session.scalars(query))
    for item in items:
        item.requires_confirmation = False
        item.status = "pending"
        item.updated_at = datetime.now(UTC)
    session.commit()
    found = {item.action_key for item in items}
    return {
        "confirmed": [item.action_key for item in items],
        "missing": [key for key in action_keys if key not in found],
        "items": [item.statement for item in items],
    }


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


def record_runtime_error(
    session: Session,
    user: User,
    stage: str,
    error: BaseException,
    telegram_message_id: int | None = None,
) -> RuntimeErrorLog:
    """Persist detailed failure information without exposing it in Telegram."""
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    record = RuntimeErrorLog(
        user_id=user.id,
        stage=stage,
        message=str(error) or error.__class__.__name__,
        exception_type=error.__class__.__name__,
        source_file=frame.filename if frame else None,
        source_line=frame.lineno if frame else None,
        traceback_text="".join(traceback.format_exception(error)),
        telegram_message_id=telegram_message_id,
    )
    session.add(record)
    session.commit()
    record_runtime_output(
        f"{stage} failed with {error.__class__.__name__}: {str(error) or error.__class__.__name__}",
        level="error",
        operation=stage,
    )
    return record


def reset_conversation(session: Session, user: User) -> str:
    """Clear conversation history while preserving memories and planning records."""
    conversation = get_or_create_conversation(session, user)
    message_ids = list(
        session.scalars(select(Message.id).where(Message.conversation_id == conversation.id))
    )
    if message_ids:
        session.query(MessageAttachment).filter(
            MessageAttachment.message_id.in_(message_ids)
        ).delete(synchronize_session=False)
        session.query(Message).filter(Message.id.in_(message_ids)).delete(synchronize_session=False)
    summary = session.scalar(
        select(ConversationSummary).where(ConversationSummary.conversation_id == conversation.id)
    )
    if summary is not None:
        session.query(SummaryUpdate).filter(SummaryUpdate.summary_id == summary.id).delete(
            synchronize_session=False
        )
        session.delete(summary)
    session.query(PendingState).filter(PendingState.conversation_id == conversation.id).delete(
        synchronize_session=False
    )
    group_ids = list(
        session.scalars(
            select(ActionGroup.id).where(ActionGroup.conversation_id == conversation.id)
        )
    )
    if group_ids:
        session.query(ActionItem).filter(ActionItem.group_id.in_(group_ids)).delete(
            synchronize_session=False
        )
        session.query(ActionGroup).filter(ActionGroup.id.in_(group_ids)).delete(
            synchronize_session=False
        )
    session.commit()
    return conversation.id


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


def save_telegram_planning_card(
    session: Session,
    user: User,
    entity_type: str,
    entity_id: str,
    chat_id: int,
    message_id: int,
) -> TelegramPlanningCard:
    card = session.scalar(
        select(TelegramPlanningCard).where(
            TelegramPlanningCard.user_id == user.id,
            TelegramPlanningCard.entity_type == entity_type,
            TelegramPlanningCard.entity_id == entity_id,
        )
    )
    if card is None:
        card = TelegramPlanningCard(
            user_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
        )
        session.add(card)
    else:
        card.telegram_chat_id = chat_id
        card.telegram_message_id = message_id
        card.status = "synced"
        card.updated_at = datetime.now(UTC)
    session.commit()
    return card


def delete_planning_record(
    session: Session, user: User, entity_type: str, entity_id: str
) -> str | None:
    record: Place | SavedIdea | Event | Reminder | None
    if entity_type == "place":
        record = session.scalar(
            select(Place).where(Place.id == entity_id, Place.user_id == user.id)
        )
    elif entity_type == "idea":
        record = session.scalar(
            select(SavedIdea).where(SavedIdea.id == entity_id, SavedIdea.user_id == user.id)
        )
    elif entity_type == "event":
        record = session.scalar(
            select(Event).where(Event.id == entity_id, Event.user_id == user.id)
        )
    elif entity_type == "reminder":
        record = session.scalar(
            select(Reminder).where(Reminder.id == entity_id, Reminder.user_id == user.id)
        )
    else:
        return None
    if record is None:
        return None
    record.status = "deleted" if entity_type in {"place", "idea"} else "cancelled"
    record.updated_at = datetime.now(UTC)
    card = session.scalar(
        select(TelegramPlanningCard).where(
            TelegramPlanningCard.user_id == user.id,
            TelegramPlanningCard.entity_type == entity_type,
            TelegramPlanningCard.entity_id == entity_id,
        )
    )
    if card is not None:
        card.status = "deleted"
        card.updated_at = datetime.now(UTC)
    session.commit()
    return str(getattr(record, "name", None) or getattr(record, "title", entity_type))


def purge_planning_record(session: Session, user: User, entity_type: str, entity_id: str) -> None:
    """Permanently remove an isolated temporary planning record."""
    record = get_owned_planning_record(session, user, entity_type, entity_id)
    if record is None:
        return
    session.query(TelegramPlanningCard).filter_by(
        user_id=user.id, entity_type=entity_type, entity_id=entity_id
    ).delete(synchronize_session=False)
    session.delete(record)
    session.commit()


def get_owned_planning_record(
    session: Session, user: User, entity_type: str, entity_id: str
) -> Place | SavedIdea | Event | Reminder | None:
    if entity_type == "place":
        return session.scalar(select(Place).where(Place.id == entity_id, Place.user_id == user.id))
    if entity_type == "idea":
        return session.scalar(
            select(SavedIdea).where(SavedIdea.id == entity_id, SavedIdea.user_id == user.id)
        )
    if entity_type == "event":
        return session.scalar(select(Event).where(Event.id == entity_id, Event.user_id == user.id))
    if entity_type == "reminder":
        return session.scalar(
            select(Reminder).where(Reminder.id == entity_id, Reminder.user_id == user.id)
        )
    return None
