"""Build compact model context from recent messages and retrieved memories."""

from dataclasses import dataclass

from wingman.models import Conversation, ConversationSummary, PendingState, User
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
    summary: ConversationSummary | None = None,
    pending_state: PendingState | None = None,
    max_messages: int = 20,
    max_memories: int = 8,
    token_budget: int = 4000,
) -> BuiltContext:
    static_context = (
        "You are a thoughtful private relationship wingman. Be natural and concise. "
        "Do not recommend manipulation, pressure, surveillance, or deception. "
        f"The user's name is {user.name or 'the user'}. "
        f"The primary person's name is configured by the owner. The timezone is {timezone}. "
        f"The current user request is {query}"
    )
    memories = retrieved[:max_memories]
    memory_lines = [f"- {item.memory.statement} ({item.memory.status})" for item in memories]
    dynamic_parts = ["Relevant saved context:\n" + ("\n".join(memory_lines) or "- None")]
    if summary is not None and summary.summary_text:
        dynamic_parts.insert(0, f"Conversation summary:\n{summary.summary_text}")
    if pending_state is not None:
        dynamic_parts.append(f"Pending question:\n{pending_state.question_asked}")
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
