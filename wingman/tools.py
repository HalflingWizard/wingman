"""Validated model action tools."""

# Tool schemas and compact dashboard payloads are intentionally kept readable inline.
# ruff: noqa: E501

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wingman.models import Conversation, User
from wingman.retrieval import retrieve_memories
from wingman.services import (
    add_memory_note,
    confirm_memory,
    create_event,
    create_memory,
    create_pending_state,
    create_place,
    create_reminder,
    create_saved_idea,
    delete_memory,
    find_event,
    find_place_by_name,
    find_reminder,
    find_saved_idea_by_title,
    get_open_pending_state,
    get_owned_memory,
    list_events,
    list_memory_notes,
    list_places,
    list_reminders,
    list_saved_ideas,
    record_tool_execution,
    update_memory,
)


class CreateMemoryInput(BaseModel):
    statement: str = Field(min_length=1, max_length=4000)
    memory_type: str = Field(default="fact", max_length=40)
    status: str = Field(default="confirmed", max_length=20)
    confidence: float = Field(default=1.0, ge=0, le=1)
    importance: int = Field(default=3, ge=1, le=5)


class UpdateMemoryInput(BaseModel):
    memory_id: str
    statement: str | None = Field(default=None, min_length=1, max_length=4000)
    memory_type: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: int | None = Field(default=None, ge=1, le=5)


class AddMemoryNoteInput(BaseModel):
    memory_id: str
    text: str = Field(min_length=1, max_length=2000)
    note_type: str = Field(default="evidence", max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SearchMemoriesInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=8)


class ProposeMemoryInput(BaseModel):
    statement: str = Field(min_length=1, max_length=4000)
    memory_type: str = Field(default="observation", max_length=40)
    status: str = Field(default="inferred", pattern="^(observed|inferred|uncertain)$")
    confidence: float = Field(default=0.7, ge=0, le=1)
    importance: int = Field(default=3, ge=1, le=5)


class SearchPlanningInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


class CreatePlaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=4000)
    place_type: str = Field(default="place", max_length=40)
    atmosphere_tags: str = Field(default="", max_length=500)


class CreateIdeaInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=4000)
    place_id: str | None = None


class CreateEventInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: str = Field(min_length=1, max_length=80)
    event_type: str = Field(default="event", max_length=40)
    timezone: str = Field(default="UTC", max_length=80)
    description: str = Field(default="", max_length=4000)
    place_id: str | None = None


class CreateReminderInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scheduled_at: str = Field(min_length=1, max_length=80)
    timezone: str = Field(default="UTC", max_length=80)
    event_id: str | None = None


class MemoryToolExecutor:
    def __init__(
        self,
        session: Session,
        user: User,
        agent_run_id: str | None = None,
        conversation: Conversation | None = None,
        source_message_id: str | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.agent_run_id = agent_run_id
        self.conversation = conversation
        self.source_message_id = source_message_id

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "search_memories":
                search_data = SearchMemoriesInput.model_validate(arguments)
                matches = retrieve_memories(
                    self.session, self.user, search_data.query, limit=search_data.top_k
                )
                output: dict[str, Any] = {
                    "memories": [
                        {
                            "memory_id": result.memory.id,
                            "statement": result.memory.statement,
                            "status": result.memory.status,
                            "confidence": result.memory.confidence,
                            "importance": result.memory.importance,
                            "notes": [
                                {
                                    "note_id": note.id,
                                    "text": note.text,
                                    "note_type": note.note_type,
                                    "source_message_id": note.source_message_id,
                                }
                                for note in list_memory_notes(
                                    self.session, self.user, result.memory.id
                                )
                            ],
                        }
                        for result in matches
                    ]
                }
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "search_planning":
                planning_data = SearchPlanningInput.model_validate(arguments)
                query = planning_data.query.casefold()
                records: list[dict[str, Any]] = []
                for place in list_places(self.session, self.user):
                    text = (
                        f"{place.name} {place.address} {place.city} {place.description}".casefold()
                    )
                    if query in text:
                        records.append(
                            {
                                "kind": "place",
                                "id": place.id,
                                "name": place.name,
                                "address": place.address,
                                "city": place.city,
                                "description": place.description,
                            }
                        )
                for idea in list_saved_ideas(self.session, self.user):
                    if query in f"{idea.title} {idea.reason}".casefold():
                        records.append(
                            {
                                "kind": "idea",
                                "id": idea.id,
                                "title": idea.title,
                                "reason": idea.reason,
                            }
                        )
                for event in list_events(self.session, self.user):
                    if query in f"{event.title} {event.description}".casefold():
                        records.append(
                            {
                                "kind": "event",
                                "id": event.id,
                                "title": event.title,
                                "start_at": event.start_at.isoformat(),
                                "description": event.description,
                            }
                        )
                for reminder in list_reminders(self.session, self.user):
                    if query in reminder.title.casefold():
                        records.append(
                            {
                                "kind": "reminder",
                                "id": reminder.id,
                                "title": reminder.title,
                                "scheduled_at": reminder.scheduled_at.isoformat(),
                            }
                        )
                output = {"records": records[: planning_data.top_k]}
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "create_place":
                place_data = CreatePlaceInput.model_validate(arguments)
                existing_place = find_place_by_name(self.session, self.user, place_data.name)
                if existing_place is not None:
                    output = {
                        "created": False,
                        "duplicate": True,
                        "place_id": existing_place.id,
                        "name": existing_place.name,
                    }
                else:
                    place = create_place(self.session, self.user, **place_data.model_dump())
                    output = {
                        "created": True,
                        "place_id": place.id,
                        "name": place.name,
                        "address": place.address,
                        "city": place.city,
                    }
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "create_saved_idea":
                idea_data = CreateIdeaInput.model_validate(arguments)
                existing_idea = find_saved_idea_by_title(self.session, self.user, idea_data.title)
                if existing_idea is not None:
                    output = {
                        "created": False,
                        "duplicate": True,
                        "idea_id": existing_idea.id,
                        "title": existing_idea.title,
                    }
                else:
                    idea = create_saved_idea(self.session, self.user, **idea_data.model_dump())
                    output = {"created": True, "idea_id": idea.id, "title": idea.title}
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "create_event":
                event_data = CreateEventInput.model_validate(arguments)
                start_at = datetime.fromisoformat(event_data.start_at)
                existing_event = find_event(self.session, self.user, event_data.title, start_at)
                if existing_event is not None:
                    output = {
                        "created": False,
                        "duplicate": True,
                        "event_id": existing_event.id,
                        "title": existing_event.title,
                    }
                else:
                    event = create_event(
                        self.session,
                        self.user,
                        event_data.title,
                        start_at,
                        event_data.event_type,
                        event_data.timezone,
                        event_data.description,
                        event_data.place_id,
                    )
                    output = {
                        "created": True,
                        "event_id": event.id,
                        "title": event.title,
                        "start_at": event.start_at.isoformat(),
                    }
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "create_reminder":
                reminder_data = CreateReminderInput.model_validate(arguments)
                scheduled_at = datetime.fromisoformat(reminder_data.scheduled_at)
                existing_reminder = find_reminder(
                    self.session, self.user, reminder_data.title, scheduled_at
                )
                if existing_reminder is not None:
                    output = {
                        "created": False,
                        "duplicate": True,
                        "reminder_id": existing_reminder.id,
                        "title": existing_reminder.title,
                    }
                else:
                    reminder = create_reminder(
                        self.session,
                        self.user,
                        reminder_data.title,
                        scheduled_at,
                        reminder_data.timezone,
                        reminder_data.event_id,
                    )
                    output = {
                        "created": True,
                        "reminder_id": reminder.id,
                        "title": reminder.title,
                        "scheduled_at": reminder.scheduled_at.isoformat(),
                    }
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            if name == "create_memory":
                create_data = CreateMemoryInput.model_validate(arguments)
                memory = create_memory(self.session, self.user, **create_data.model_dump())
                if self.conversation is not None:
                    pending_memory = get_open_pending_state(
                        self.session, self.user, self.conversation
                    )
                    if (
                        pending_memory is not None
                        and pending_memory.state_type == "memory_proposal"
                    ):
                        pending_memory.status = "completed"
                        self.session.commit()
                if self.source_message_id is not None:
                    add_memory_note(
                        self.session,
                        self.user,
                        memory.id,
                        "Captured from the owner's message.",
                        note_type="source",
                        source_message_id=self.source_message_id,
                    )
            elif name == "propose_memory":
                if self.conversation is None:
                    raise ValueError("A conversation is required for a memory proposal")
                proposal = ProposeMemoryInput.model_validate(arguments)
                existing_proposal = get_open_pending_state(
                    self.session, self.user, self.conversation
                )
                if (
                    existing_proposal is not None
                    and existing_proposal.state_type == "memory_proposal"
                ):
                    output = {
                        "pending_state_id": existing_proposal.id,
                        "statement": existing_proposal.missing_information,
                        "status": "already_proposed",
                    }
                    record_tool_execution(
                        self.session,
                        self.user,
                        name,
                        arguments,
                        output_data=output,
                        agent_run_id=self.agent_run_id,
                    )
                    return output
                state = create_pending_state(
                    self.session,
                    self.user,
                    self.conversation,
                    "memory_proposal",
                    proposal.statement,
                    f"Would you like me to save this memory? {proposal.statement}",
                    datetime.now(UTC) + timedelta(hours=24),
                )
                output = {
                    "pending_state_id": state.id,
                    "statement": proposal.statement,
                    "status": "awaiting_confirmation",
                }
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            elif name == "dismiss_memory_proposal":
                if self.conversation is None:
                    raise ValueError("A conversation is required to dismiss a proposal")
                pending = get_open_pending_state(self.session, self.user, self.conversation)
                if pending is None or pending.state_type != "memory_proposal":
                    output = {"dismissed": False}
                else:
                    pending.status = "dismissed"
                    self.session.commit()
                    output = {"dismissed": True}
                record_tool_execution(
                    self.session,
                    self.user,
                    name,
                    arguments,
                    output_data=output,
                    agent_run_id=self.agent_run_id,
                )
                return output
            elif name == "update_memory":
                update_data = UpdateMemoryInput.model_validate(arguments)
                fields = update_data.model_dump(exclude_none=True)
                memory_id = fields.pop("memory_id")
                if "memory_type" in fields:
                    fields["type"] = fields.pop("memory_type")
                memory = update_memory(self.session, self.user, memory_id, **fields)
            elif name == "delete_memory":
                memory = delete_memory(self.session, self.user, str(arguments["memory_id"]))
            elif name == "confirm_memory":
                memory = confirm_memory(self.session, self.user, str(arguments["memory_id"]))
            elif name == "add_memory_note":
                note_data = AddMemoryNoteInput.model_validate(arguments)
                add_memory_note(
                    self.session,
                    self.user,
                    **note_data.model_dump(),
                    source_message_id=self.source_message_id,
                )
                note_memory = get_owned_memory(self.session, self.user, note_data.memory_id)
                if note_memory is None:
                    raise ValueError("Memory does not exist")
                memory = note_memory
            else:
                raise ValueError("Unknown tool")
            output = {"memory_id": memory.id, "status": memory.status}
            record_tool_execution(
                self.session,
                self.user,
                name,
                arguments,
                output_data=output,
                agent_run_id=self.agent_run_id,
            )
            return output
        except Exception as exc:
            record_tool_execution(
                self.session,
                self.user,
                name,
                arguments,
                status="failed",
                error=str(exc),
                agent_run_id=self.agent_run_id,
            )
            raise
