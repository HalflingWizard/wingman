"""OpenAI Responses API adapter."""

import json
from collections.abc import Callable
from typing import Any, cast

from openai import AsyncOpenAI

from wingman.config import Settings

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]

MEMORY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_memories",
        "description": "Search the owner's saved memories and notes before creating a duplicate.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_memory",
        "description": (
            "Ask the owner whether to save an uncertain personal observation or preference. "
            "Use this before saving a detail such as Matt's opinion about someone's clothing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
                "memory_type": {"type": "string"},
                "status": {"type": "string", "enum": ["observed", "inferred", "uncertain"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "importance": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": [
                "statement",
                "memory_type",
                "status",
                "confidence",
                "importance",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_memory",
        "description": "Create a saved memory after the user clearly states a durable detail.",
        "parameters": {
            "type": "object",
            "properties": {
                "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
                "memory_type": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["confirmed", "observed", "inferred", "uncertain"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "importance": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": [
                "statement",
                "memory_type",
                "status",
                "confidence",
                "importance",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "add_memory_note",
        "description": "Add evidence or source context to an existing memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                "note_type": {"type": "string"},
                "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            },
            "required": ["memory_id", "text", "note_type", "confidence"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "update_memory",
        "description": "Update an existing owned memory when the user corrects or clarifies it.",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "statement": {"type": ["string", "null"]},
                "memory_type": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "confidence": {"type": ["number", "null"]},
                "importance": {"type": ["integer", "null"]},
            },
            "required": [
                "memory_id",
                "statement",
                "memory_type",
                "status",
                "confidence",
                "importance",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "dismiss_memory_proposal",
        "description": "Dismiss the open memory proposal when the owner declines to save it.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "confirm_memory",
        "description": "Confirm an inferred memory after the user clearly confirms it.",
        "parameters": {
            "type": "object",
            "properties": {"memory_id": {"type": "string"}},
            "required": ["memory_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is not configured")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=2)
        self.model = settings.openai_main_model
        self.summary_model = settings.openai_summary_model
        self.last_usage: tuple[int | None, int | None] = (None, None)
        self.last_request_snapshot: dict[str, Any] = {}

    async def reply(
        self,
        messages: list[tuple[str, str]],
        user_name: str,
        person_name: str,
        static_context: str = "",
        dynamic_context: str = "",
        tool_executor: ToolExecutor | None = None,
    ) -> str:
        self.last_tool_trace: list[dict[str, Any]] = []
        prompt = (
            f"{static_context} "
            "Memory tool guidance. Use search_memories when the current context may be "
            "missing a relevant saved detail or when checking for a duplicate. Use "
            "create_memory for a clear durable preference or fact, including a direct "
            "reported preference such as she told me she likes tomatoes. Do not create "
            "memories for greetings, generic brainstorming, temporary plans, or minor "
            "conversation details. For Matt's own subjective opinion or an observation he "
            "has not asked to save, use propose_memory first. Use observed or inferred for "
            "a new unconfirmed detail. "
            "Use add_memory_note when new evidence supports an existing memory. Use "
            "propose_memory for a personal observation or preference that should be saved "
            "only after Matt agrees. If there is an open proposal, use the exact proposed "
            "statement when Matt agrees, or dismiss_memory_proposal when he declines. "
            "confirm_memory only after the user confirms it. Keep the final reply natural "
            "and never mention the internal tool call. "
            f"The user's name is {user_name or 'the user'}. The person discussed is "
            f"{person_name or 'someone important to the user'}."
        )
        input_messages: list[dict[str, str]] = []
        if dynamic_context:
            input_messages.append(
                {
                    "role": "developer",
                    "content": (
                        "The following dynamic context was retrieved for this turn. "
                        "Use it when relevant. Do not mention retrieval mechanics or scores.\n"
                        + dynamic_context
                    ),
                }
            )
        input_messages.extend({"role": role, "content": text} for role, text in messages[-20:])
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": prompt,
            "input": cast(Any, input_messages),
            "reasoning": {"effort": "low", "summary": "auto"},
            "text": {"verbosity": "low"},
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if tool_executor is not None:
            request["tools"] = MEMORY_TOOLS
            request["tool_choice"] = "auto"
            request["parallel_tool_calls"] = False
        self.last_request_snapshot = request
        response = await self.client.responses.create(**request)
        if tool_executor is not None:
            for _ in range(4):
                calls = [
                    item
                    for item in getattr(response, "output", [])
                    if getattr(item, "type", None) == "function_call"
                ]
                if not calls:
                    break
                follow_up: list[Any] = list(response.output)
                for call in calls:
                    arguments: dict[str, Any] = {}
                    try:
                        parsed = json.loads(call.arguments)
                        if not isinstance(parsed, dict):
                            raise ValueError("Tool arguments must be a JSON object")
                        arguments = parsed
                        result = tool_executor(call.name, arguments)
                        output = {"ok": True, "result": result}
                    except Exception as exc:
                        output = {"ok": False, "error": str(exc)}
                    self.last_tool_trace.append(
                        {"name": call.name, "arguments": arguments, "output": output}
                    )
                    follow_up.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(output, sort_keys=True),
                        }
                    )
                response = await self.client.responses.create(
                    **request | {"input": cast(Any, follow_up)}
                )
        usage = response.usage
        self.last_usage = (
            getattr(usage, "input_tokens", None) if usage else None,
            getattr(usage, "output_tokens", None) if usage else None,
        )
        return str(response.output_text).strip()

    async def summarize(self, existing_summary: str, messages: list[tuple[str, str]]) -> str:
        input_text = "\n".join(f"{sender}: {text}" for sender, text in messages)
        response = await self.client.responses.create(
            model=self.summary_model,
            instructions=(
                "Update a concise rolling conversation summary. Keep current topic, user goal, "
                "emotional context, decisions, corrections, open questions, commitments, and "
                "temporary details. Do not repeat durable memories unnecessarily."
            ),
            input=f"Existing summary\n{existing_summary}\n\nMessages\n{input_text}",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
            store=False,
            include=["reasoning.encrypted_content"],
        )
        usage = response.usage
        self.last_usage = (
            getattr(usage, "input_tokens", None) if usage else None,
            getattr(usage, "output_tokens", None) if usage else None,
        )
        return response.output_text.strip()

    async def embed(
        self, text: str, embedding_model: str = "text-embedding-3-small"
    ) -> list[float]:
        response = await self.client.embeddings.create(model=embedding_model, input=text)
        return response.data[0].embedding
