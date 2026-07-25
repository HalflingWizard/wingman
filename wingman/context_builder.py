"""Build compact model context from recent messages and retrieved memories."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from wingman.models import (
    Conversation,
    ConversationSummary,
    Event,
    PendingState,
    Place,
    Reminder,
    SavedIdea,
    User,
)
from wingman.retrieval import RetrievalResult


@dataclass(frozen=True)
class BuiltContext:
    static_context: str
    dynamic_context: str
    messages: list[tuple[str, str]]
    memories: list[RetrievalResult]
    summary: ConversationSummary | None
    pending_state: PendingState | None
    estimated_tokens: int


def build_context(
    user: User,
    conversation: Conversation,
    query: str,
    retrieved: list[RetrievalResult],
    timezone: str,
    primary_person_name: str = "",
    summary: ConversationSummary | None = None,
    pending_state: PendingState | None = None,
    places: list[Place] | None = None,
    ideas: list[SavedIdea] | None = None,
    events: list[Event] | None = None,
    reminders: list[Reminder] | None = None,
    max_messages: int = 20,
    max_memories: int = 8,
    token_budget: int = 4000,
) -> BuiltContext:
    try:
        current_time = datetime.now(ZoneInfo(timezone)).isoformat(timespec="minutes")
    except Exception:
        current_time = datetime.now().astimezone().isoformat(timespec="minutes")
    static_context = (
        "You are a thoughtful private relationship wingman. Be natural and concise. "
        "Do not recommend manipulation, pressure, surveillance, or deception. "
        "Keep facts, observations, and inferences separate. Do not treat one observation "
        "as proof of a general preference. Use relevant saved context when it helps answer "
        "the user's question, and explain the connection naturally. "
        f"The user's name is {user.name or 'the user'}. "
        f"The primary person's name is {primary_person_name or 'not configured'}. "
        f"The user's timezone is {timezone}. The current local date and time is {current_time}."
    )
    memories = retrieved[:max_memories]
    memory_lines = [f"- {item.memory.statement} ({item.memory.status})" for item in memories]
    dynamic_parts = ["Relevant saved context:\n" + ("\n".join(memory_lines) or "- None")]
    if summary is not None and summary.summary_text:
        dynamic_parts.insert(0, f"Conversation summary:\n{summary.summary_text}")
    if pending_state is not None:
        dynamic_parts.append(f"Pending question:\n{pending_state.question_asked}")
    if places:
        dynamic_parts.append(
            "Saved places:\n"
            + "\n".join(f"- {place.name}. {place.description}" for place in places)
        )
    if ideas:
        dynamic_parts.append(
            "Saved ideas:\n" + "\n".join(f"- {idea.title}. {idea.reason}" for idea in ideas)
        )
    if events:
        dynamic_parts.append(
            "Upcoming events:\n"
            + "\n".join(f"- {event.title} at {event.start_at.isoformat()}" for event in events)
        )
    if reminders:
        dynamic_parts.append(
            "Upcoming reminders:\n"
            + "\n".join(
                f"- {reminder.title} at {reminder.scheduled_at.isoformat()}"
                for reminder in reminders
            )
        )
    dynamic = "\n\n".join(dynamic_parts)
    messages = [(message.sender, message.text) for message in conversation.messages[-max_messages:]]
    while (
        messages
        and (len(static_context) + len(dynamic) + sum(len(text) for _, text in messages)) // 4
        > token_budget
    ):
        messages.pop(0)
    estimated_tokens = max(
        1,
        (len(static_context) + len(dynamic) + sum(len(text) for _, text in messages)) // 4,
    )
    return BuiltContext(
        static_context,
        dynamic,
        messages,
        memories,
        summary,
        pending_state,
        estimated_tokens,
    )
