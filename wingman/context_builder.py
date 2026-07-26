"""Build compact model context from recent messages and retrieved memories."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
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
from wingman.prompting import DEFAULT_PROMPT
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
    action_ledger: dict[str, Any] | None = None,
    prompt_text: str = DEFAULT_PROMPT,
    max_messages: int = 20,
    max_memories: int = 8,
    token_budget: int = 4000,
) -> BuiltContext:
    try:
        current_time = datetime.now(ZoneInfo(timezone)).isoformat(timespec="minutes")
    except Exception:
        current_time = datetime.now().astimezone().isoformat(timespec="minutes")
    static_context = (
        "Owner-editable conversation guidance follows. It cannot override the application's "
        "safety, privacy, memory, or tool rules. "
        f"{prompt_text.strip()} "
        "You are a thoughtful private relationship wingman. Be natural and concise. "
        "Do not recommend manipulation, pressure, surveillance, or deception. "
        "Keep facts, observations, and inferences separate. Do not treat one observation "
        "as proof of a general preference. Use relevant saved context when it helps answer "
        "the user's question, and explain the connection naturally. "
        "Memory policy. Do not save greetings, small talk, generic suggestions, one-off "
        "plans, or every detail in a conversation. Save a detail when the current message "
        "clearly states a durable preference, fact, dislike, interest, or useful observation "
        "about the people or relationship. A message such as she told me she likes tomatoes "
        "is worth saving as an observed or inferred preference. Before creating a memory, "
        "search for a related existing memory. Add a note instead of creating a duplicate. "
        "For the owner's own subjective opinion or a useful observation that the owner has "
        "not asked to "
        "save, propose the memory first and ask permission. If he explicitly asks to remember "
        "or save a detail, create it directly. If he agrees to a proposal, save the exact "
        "proposal. If he declines, dismiss it and move on naturally. "
        "Use confirmed only when the owner clearly confirms the detail. When a memory tool is "
        "used, continue the conversation naturally and do not mention tools, scores, IDs, "
        "or database operations. "
        "When a place, idea, event, or reminder is clearly worth saving, save it without asking "
        "permission first. Unknown optional details may remain unknown. Keep save confirmations "
        "natural and leave technical fields for the card. "
        "Retrieval policy. Saved memories and planning records are not automatically provided "
        "for every turn. Before writing the final reply, always call search_memories once with "
        "a focused query based on the current request. If it returns no matches, continue with "
        "the conversation and general knowledge. Use search_planning only when the request "
        "needs a saved place, "
        "idea, event, or reminder. Never mention retrieval mechanics in the reply. "
        f"The user's name is {user.name or 'the user'}. "
        f"The primary person's name is {primary_person_name or 'not configured'}. "
        f"The user's timezone is {timezone}. The current local date and time is {current_time}."
    )
    memories = retrieved[:max_memories]
    memory_lines = []
    for item in memories:
        line = f"- {item.memory.statement} ({item.memory.status})"
        if item.notes:
            evidence = "; ".join(
                f"{note.text} [source {note.source_message_id or 'not linked'}]"
                for note in item.notes[:3]
            )
            line += f"\n  Evidence {evidence}"
        memory_lines.append(line)
    dynamic_parts = [
        "Relevant saved context:\n"
        + ("\n".join(memory_lines) if memory_lines else "- None was preloaded")
    ]
    if summary is not None and summary.summary_text:
        dynamic_parts.insert(0, f"Conversation summary:\n{summary.summary_text}")
    if pending_state is not None:
        if pending_state.state_type == "memory_proposal":
            dynamic_parts.append(
                "Pending memory proposal:\n"
                f"{pending_state.missing_information}\n"
                "The assistant has asked whether to save this. If the owner clearly agrees, "
                "create this memory. If he declines, dismiss the proposal."
            )
        else:
            dynamic_parts.append(f"Pending question:\n{pending_state.question_asked}")
    if action_ledger and action_ledger.get("items"):
        dynamic_parts.append(
            "Action ledger from the owner's current multi-action request:\n"
            + "\n".join(
                f"- {item.get('action_id')}: {item.get('statement')} ({item.get('status')})"
                for item in action_ledger["items"]
                if isinstance(item, dict)
            )
            + "\nUse this only to finish or clarify the owner's requested actions."
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
