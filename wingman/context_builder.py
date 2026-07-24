"""Build compact model context from recent messages and retrieved memories."""

from dataclasses import dataclass

from wingman.models import Conversation, User
from wingman.retrieval import RetrievalResult


@dataclass(frozen=True)
class BuiltContext:
    static_context: str
    messages: list[tuple[str, str]]
    memories: list[RetrievalResult]
    estimated_tokens: int


def build_context(
    user: User,
    conversation: Conversation,
    query: str,
    retrieved: list[RetrievalResult],
    timezone: str,
    max_messages: int = 20,
    max_memories: int = 8,
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
    dynamic = "Relevant saved context:\n" + ("\n".join(memory_lines) or "- None")
    messages = [(message.sender, message.text) for message in conversation.messages[-max_messages:]]
    estimated_tokens = max(
        1,
        (len(static_context) + len(dynamic) + sum(len(text) for _, text in messages)) // 4,
    )
    return BuiltContext(static_context + "\n" + dynamic, messages, memories, estimated_tokens)
