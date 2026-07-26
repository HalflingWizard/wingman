"""OpenAI Responses API adapter."""

# Tool schemas are intentionally kept inline for API snapshot readability.
# ruff: noqa: E501

import base64
import json
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from openai import AsyncOpenAI

from wingman.config import Settings
from wingman.inbound import InboundAttachment

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]

MEMORY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "register_actions",
        "description": (
            "Register every distinct action requested in the current message before executing "
            "multiple memory or planning writes. Use one item per requested detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_id": {"type": "string", "minLength": 1, "maxLength": 100},
                            "action_type": {"type": "string", "maxLength": 40},
                            "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "requires_confirmation": {"type": "boolean"},
                        },
                        "required": [
                            "action_id",
                            "action_type",
                            "statement",
                            "requires_confirmation",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["actions"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "confirm_actions",
        "description": "Confirm pending action items so the application can complete them.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_ids": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string", "maxLength": 100},
                }
            },
            "required": ["action_ids"],
            "additionalProperties": False,
        },
        "strict": True,
    },
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
            "Use this only when the owner has not explicitly asked to save it. Do not use it "
            "for a direct request to remember or save a detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
                "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
                "memory_type": {"type": "string"},
                "status": {"type": "string", "enum": ["observed", "inferred", "uncertain"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "importance": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": [
                "action_id",
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
        "description": "Create a saved memory after the user clearly states a durable detail or explicitly asks to remember it.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
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
                "action_id",
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

PLANNING_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_planning",
        "description": "Search the owner's places, ideas, events, and reminders before creating duplicates.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_place",
        "description": "Save a useful place. Address and city may be unknown and can be added later.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
                "name": {"type": "string", "minLength": 1, "maxLength": 200},
                "address": {"type": "string", "maxLength": 500},
                "city": {"type": "string", "maxLength": 120},
                "description": {"type": "string", "maxLength": 4000},
                "place_type": {"type": "string", "maxLength": 40},
                "atmosphere_tags": {"type": "string", "maxLength": 500},
            },
            "required": [
                "action_id",
                "name",
                "address",
                "city",
                "description",
                "place_type",
                "atmosphere_tags",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_saved_idea",
        "description": "Save a useful date or relationship idea after clear owner intent.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "reason": {"type": "string", "maxLength": 4000},
                "place_id": {"type": ["string", "null"]},
            },
            "required": ["action_id", "title", "reason", "place_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_event",
        "description": "Create an event only when the owner provides a definite date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "start_at": {"type": "string", "minLength": 1, "maxLength": 80},
                "event_type": {"type": "string", "maxLength": 40},
                "timezone": {"type": "string", "maxLength": 80},
                "description": {"type": "string", "maxLength": 4000},
                "place_id": {"type": ["string", "null"]},
            },
            "required": [
                "action_id",
                "title",
                "start_at",
                "event_type",
                "timezone",
                "description",
                "place_id",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_reminder",
        "description": "Create a reminder only when the owner provides a definite date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {"type": ["string", "null"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "scheduled_at": {"type": "string", "minLength": 1, "maxLength": 80},
                "timezone": {"type": "string", "maxLength": 80},
                "event_id": {"type": ["string", "null"]},
            },
            "required": ["action_id", "title", "scheduled_at", "timezone", "event_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

AVAILABLE_TOOLS = MEMORY_TOOLS[2:] + MEMORY_TOOLS[:2] + PLANNING_TOOLS


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is not configured")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=2)
        self.model = settings.openai_main_model
        self.summary_model = settings.openai_summary_model
        self.last_usage: tuple[int | None, int | None] = (None, None)
        self.last_request_snapshot: dict[str, Any] = {}
        self.last_transcription_snapshot: dict[str, Any] = {}
        self.last_image_snapshot: dict[str, Any] = {"count": 0, "images": []}

    async def reply(
        self,
        messages: list[tuple[str, str]],
        user_name: str,
        person_name: str,
        static_context: str = "",
        dynamic_context: str = "",
        tool_executor: ToolExecutor | None = None,
        attachments: tuple[InboundAttachment, ...] = (),
    ) -> str:
        self.last_tool_trace: list[dict[str, Any]] = []
        prompt = (
            f"{static_context} "
            "Memory tool guidance. Use search_memories when the current context may be "
            "missing a relevant saved detail or when checking for a duplicate. Use "
            "create_memory for a clear durable preference or fact, including a direct "
            "reported preference such as she told me she likes tomatoes. Do not create "
            "memories for greetings, generic brainstorming, temporary plans, or minor "
            "conversation details. For the owner's own subjective opinion or an observation the owner "
            "has not asked to save, use propose_memory first. Use observed or inferred for "
            "a new unconfirmed detail. "
            "When the owner explicitly says remember, save, add, or keep a detail, use "
            "create_memory directly instead of propose_memory. If one message contains "
            "several explicit save requests, create each valid memory. "
            "Use planning tools when the owner clearly wants a place, idea, event, or reminder "
            "saved. A statement such as finding a place the owner wants to visit is clear intent "
            "to save that place, so create it without asking permission first. Search planning "
            "records before creating duplicates. Places may have unknown addresses or cities, "
            "and should still be saved when the name is useful. Do not invent missing dates or "
            "times for events and reminders. "
            "When one message contains several distinct durable details, handle each safe "
            "detail and use multiple tool calls when appropriate. Do not stop after the "
            "first valid memory action. "
            "When two or more requested saves or planning actions are present, first use "
            "register_actions with every distinct action and a stable action_id. Then execute "
            "each registered action using its action_id. If an action ledger says items remain "
            "pending, continue tool work until all items are completed or need clarification. "
            "When the owner clearly agrees to a group of pending proposals, use confirm_actions "
            "with all matching action IDs, then continue saving every confirmed item. Never ask "
            "the owner to repeat a list that is already in the action ledger. "
            "Use add_memory_note when new evidence supports an existing memory. Use "
            "propose_memory for a personal observation or preference that should be saved "
            "only after the owner agrees. If there is an open proposal, use the exact proposed "
            "statement when the owner agrees, or dismiss_memory_proposal when the owner declines. "
            "confirm_memory only after the user confirms it. Keep the final reply natural "
            "and never mention the internal tool call, parameters, confidence, importance, "
            "database status, or record IDs. After saving, use one or two natural sentences "
            "and let the card provide the details and controls. "
            f"The user's name is {user_name or 'the user'}. The person discussed is "
            f"{person_name or 'someone important to the user'}."
        )
        input_messages: list[dict[str, Any]] = []
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
        image_attachments = tuple(
            attachment
            for attachment in attachments
            if (attachment.content_type or "").casefold().startswith("image/")
        )
        if image_attachments:
            if not input_messages or input_messages[-1].get("role") != "user":
                raise ValueError("Image input must be attached to a user message")
            content: list[dict[str, Any]] = []
            caption = str(input_messages[-1].get("content") or "").strip()
            if caption:
                content.append({"type": "input_text", "text": caption})
            image_diagnostics: list[dict[str, Any]] = []
            for attachment in image_attachments:
                if not attachment.local_path:
                    raise ValueError("Image input is missing its temporary file")
                image_bytes = Path(attachment.local_path).read_bytes()
                content.append(
                    {
                        "type": "input_image",
                        "image_url": (
                            f"data:{attachment.content_type or 'image/jpeg'};base64,"
                            + base64.b64encode(image_bytes).decode("ascii")
                        ),
                        "detail": "low",
                    }
                )
                image_diagnostics.append(
                    {
                        "filename": attachment.filename,
                        "content_type": attachment.content_type,
                        "provider_file_id": attachment.provider_file_id,
                        "size_bytes": len(image_bytes),
                        "width": attachment.width,
                        "height": attachment.height,
                        "raw_bytes_retained": False,
                    }
                )
            input_messages[-1] = {"role": "user", "content": content}
            self.last_image_snapshot = {
                "count": len(image_diagnostics),
                "images": image_diagnostics,
                "raw_bytes_retained": False,
            }
        else:
            self.last_image_snapshot = {"count": 0, "images": [], "raw_bytes_retained": False}
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
            request["tools"] = AVAILABLE_TOOLS
            request["tool_choice"] = "auto"
            request["parallel_tool_calls"] = True
        snapshot_input: list[dict[str, Any]] = []
        for item in input_messages:
            snapshot_item = dict(item)
            if isinstance(snapshot_item.get("content"), list):
                snapshot_content = []
                for content_item in snapshot_item["content"]:
                    safe_item = dict(content_item)
                    if safe_item.get("type") == "input_image":
                        safe_item["image_url"] = "[image bytes omitted]"
                    snapshot_content.append(safe_item)
                snapshot_item["content"] = snapshot_content
            snapshot_input.append(snapshot_item)
        snapshot_request = dict(request)
        snapshot_request["input"] = snapshot_input
        snapshot_request["image_diagnostics"] = self.last_image_snapshot
        self.last_request_snapshot = snapshot_request
        response = await self.client.responses.create(**request)
        if tool_executor is not None:
            action_tracking_active = False
            for _ in range(8):
                calls = [
                    item
                    for item in getattr(response, "output", [])
                    if getattr(item, "type", None) == "function_call"
                ]
                if not calls:
                    if not action_tracking_active:
                        break
                    try:
                        ledger_result = tool_executor("__action_ledger__", {})
                        ledger = (
                            ledger_result
                            if isinstance(ledger_result, dict)
                            and "continue_required" in ledger_result
                            else {"continue_required": False}
                        )
                    except Exception:
                        ledger = {"continue_required": False}
                    if not ledger.get("continue_required"):
                        break
                    follow_up = list(response.output)
                    follow_up.append(
                        {
                            "role": "developer",
                            "content": (
                                "The action ledger still has pending requested actions. "
                                "Continue using the available tools until every pending action "
                                "is completed or needs clarification. Do not ask the owner to "
                                "repeat the same request. Ledger:\n"
                                + json.dumps(ledger, sort_keys=True)
                            ),
                        }
                    )
                    response = await self.client.responses.create(
                        **request | {"input": cast(Any, follow_up)}
                    )
                    continue
                follow_up = list(response.output)
                for call in calls:
                    arguments: dict[str, Any] = {}
                    action_id: str | None = None
                    try:
                        parsed = json.loads(call.arguments)
                        if not isinstance(parsed, dict):
                            raise ValueError("Tool arguments must be a JSON object")
                        arguments = parsed
                        raw_action_id = arguments.get("action_id")
                        action_id = str(raw_action_id) if raw_action_id else None
                        if call.name == "register_actions" or action_id:
                            action_tracking_active = True
                        result = tool_executor(call.name, arguments)
                        output = {"ok": True, "result": result}
                    except Exception as exc:
                        output = {"ok": False, "error": str(exc)}
                    if action_id:
                        action_status = "failed" if not output["ok"] else "completed"
                        result_data = output.get("result")
                        if isinstance(result_data, dict):
                            if result_data.get("duplicate"):
                                action_status = "duplicate"
                            elif result_data.get("status") == "awaiting_confirmation":
                                action_status = "awaiting_confirmation"
                            elif result_data.get("needs_clarification"):
                                action_status = "needs_clarification"
                        try:
                            tool_executor(
                                "__mark_action__",
                                {
                                    "action_id": action_id,
                                    "status": action_status,
                                    "result": output.get("result"),
                                    "error": output.get("error"),
                                },
                            )
                        except Exception:
                            pass
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

    async def transcribe(self, audio: bytes, filename: str, model: str) -> str:
        started = perf_counter()
        self.last_transcription_snapshot = {
            "model": model,
            "filename": filename,
            "audio_bytes": len(audio),
            "audio_retained": False,
        }
        try:
            response = await self.client.audio.transcriptions.create(
                model=model,
                file=(filename, audio),
            )
            transcript = getattr(response, "text", "")
            if not isinstance(transcript, str) or not transcript.strip():
                raise RuntimeError("The transcription response was empty")
            self.last_transcription_snapshot["response"] = {
                "transcript_chars": len(transcript.strip()),
                "audio_retained": False,
                "latency_ms": round((perf_counter() - started) * 1000),
            }
            return transcript.strip()
        except Exception as exc:
            self.last_transcription_snapshot["error"] = str(exc)
            self.last_transcription_snapshot["latency_ms"] = round(
                (perf_counter() - started) * 1000
            )
            raise
