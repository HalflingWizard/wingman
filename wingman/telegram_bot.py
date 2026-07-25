"""Telegram polling and owner authorization."""

import asyncio
import json
from collections.abc import Awaitable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from io import BytesIO
from time import perf_counter
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.types import (
    Message as TelegramMessage,
)

from wingman.config import Settings
from wingman.context_builder import build_context
from wingman.database import session_factory
from wingman.inbound import InboundAttachment, InboundMessage, cleanup_inbound_attachments
from wingman.lifecycle import is_paused
from wingman.model_client import AVAILABLE_TOOLS, ModelClient
from wingman.models import Event, Memory, Place, Reminder, SavedIdea, now_utc
from wingman.prompting import load_prompt
from wingman.retrieval import (
    log_retrieval,
    retrieval_context_usage,
    retrieval_query,
    retrieve_memories,
)
from wingman.services import (
    add_message,
    create_agent_run,
    create_memory,
    delete_planning_record,
    finish_agent_run,
    get_open_pending_state,
    get_or_create_conversation,
    get_or_create_summary,
    get_or_create_user,
    get_owned_memory,
    get_owned_planning_record,
    mark_card_cleaned,
    mark_card_deleted,
    pending_deleted_cards,
    planning_context,
    save_message_attachments,
    save_summary,
    save_telegram_card,
    save_telegram_planning_card,
    set_memory_embedding,
)
from wingman.tools import MemoryToolExecutor


def memory_card(memory: Memory) -> tuple[str, InlineKeyboardMarkup]:
    status = memory.status.capitalize()
    text = f"🧠 {memory.statement}\n\nStatus {status}"
    buttons = []
    if memory.status == "inferred":
        buttons.append(
            InlineKeyboardButton(text="Confirm", callback_data=f"memory:confirm:{memory.id}")
        )
    if memory.status != "deleted":
        buttons.append(
            InlineKeyboardButton(text="Delete", callback_data=f"memory:delete:{memory.id}")
        )
    return text, InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


def planning_card(
    entity_type: str, record: Place | SavedIdea | Event | Reminder
) -> tuple[str, InlineKeyboardMarkup]:
    icons = {"place": "📍", "idea": "💡", "event": "📅", "reminder": "⏰"}
    labels = {"place": "Place", "idea": "Idea", "event": "Event", "reminder": "Reminder"}
    if entity_type == "place":
        assert isinstance(record, Place)
        details = [
            f"Type {record.place_type or 'place'}",
            f"Location {record.city or record.address or 'unknown'}",
        ]
        if record.description:
            details.append(record.description)
    elif entity_type == "idea":
        assert isinstance(record, SavedIdea)
        details = [record.reason] if record.reason else []
    elif entity_type == "event":
        assert isinstance(record, Event)
        details = [f"When {record.start_at.isoformat()}"]
        if record.description:
            details.append(record.description)
    else:
        assert isinstance(record, Reminder)
        details = [f"When {record.scheduled_at.isoformat()}"]
    title = record.name if isinstance(record, Place) else record.title
    text = f"{icons[entity_type]} {labels[entity_type]}\n\n{title}"
    if details:
        text += "\n\n" + "\n".join(details)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"planning:delete:{entity_type}:{record.id}",
                )
            ]
        ]
    )
    return text, keyboard


async def send_typing(message: TelegramMessage) -> None:
    if message.bot is None:
        return
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except Exception:
        pass


async def with_typing[T](message: TelegramMessage, operation: Awaitable[T]) -> T:
    async def refresh() -> None:
        while True:
            await send_typing(message)
            await asyncio.sleep(4)

    task = asyncio.create_task(refresh())
    try:
        return await operation
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def transcribe_voice(
    message: TelegramMessage, model_client: ModelClient, settings: Settings
) -> InboundMessage:
    if message.voice is None or message.bot is None:
        raise ValueError("Voice message is not available")
    if message.voice.file_size and message.voice.file_size > settings.voice_max_bytes:
        raise ValueError("Voice message is too large")
    remote_file = await message.bot.get_file(message.voice.file_id)
    if not remote_file.file_path:
        raise RuntimeError("Telegram did not provide a voice file path")
    buffer = BytesIO()
    try:
        await message.bot.download_file(remote_file.file_path, destination=buffer)
        audio = buffer.getvalue()
        if len(audio) > settings.voice_max_bytes:
            raise ValueError("Voice message is too large")
        transcript = await model_client.transcribe(
            audio, "wingman-voice.ogg", settings.openai_transcription_model
        )
    finally:
        buffer.close()
        audio = b""
    attachment = InboundAttachment(
        source_type="telegram_voice",
        provider_file_id=message.voice.file_id,
        filename="wingman-voice.ogg",
        content_type="audio/ogg",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.attachment_retention_seconds),
    )
    return InboundMessage(
        text=transcript,
        source_type="telegram_voice",
        provider_message_id=message.message_id,
        attachments=(attachment,),
    )


def build_dispatcher(settings: Settings) -> Dispatcher:
    dispatcher = Dispatcher()
    router = Router()
    sessions = session_factory(settings)
    model_client = ModelClient(settings) if settings.openai_api_key else None

    @router.message(CommandStart())
    async def start(message: TelegramMessage) -> None:
        if message.from_user is None or message.from_user.id != settings.telegram_owner_id:
            return
        await message.answer("I am ready. Tell me what is on your mind.")

    @router.message(Command("remember"))
    async def remember(message: TelegramMessage) -> None:
        if message.from_user is None or message.from_user.id != settings.telegram_owner_id:
            return
        statement = (message.text or "").partition(" ")[2].strip()
        if not statement:
            await message.answer("Use /remember followed by the detail you want to save.")
            return
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id, settings.user_name)
            memory = create_memory(session, user, statement)
            memory_id = memory.id
            card_text, keyboard = memory_card(memory)
        if model_client is not None:
            try:
                vector = await model_client.embed(memory.statement, settings.openai_embedding_model)
                with sessions() as session:
                    user = get_or_create_user(session, message.from_user.id)
                    set_memory_embedding(session, user, memory_id, vector)
            except Exception:
                pass
        card = await message.answer(card_text, reply_markup=keyboard)
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id)
            owned_memory = get_owned_memory(session, user, memory_id)
            if owned_memory is not None:
                save_telegram_card(session, owned_memory, message.chat.id, card.message_id)

    @router.callback_query(F.data.startswith("memory:"))
    async def memory_callback(callback: CallbackQuery) -> None:
        if (
            callback.from_user.id != settings.telegram_owner_id
            or callback.message is None
            or not isinstance(callback.message, TelegramMessage)
        ):
            await callback.answer()
            return
        _, action, memory_id = (callback.data or "").split(":", 2)
        with sessions() as session:
            user = get_or_create_user(session, callback.from_user.id)
            memory = get_owned_memory(session, user, memory_id)
            if memory is None:
                await callback.answer("Memory not found", show_alert=True)
                return
            if action == "delete":
                memory.status = "deleted"
                memory.deleted_at = now_utc()
                session.commit()
                mark_card_deleted(session, memory.id)
                text = f"🗑️ Deleted memory\n\n{memory.statement}"
                try:
                    await callback.message.edit_text(text, reply_markup=None)
                except Exception:
                    pass
                await callback.answer("Memory deleted")
                return
            if action == "confirm" and memory.status == "inferred":
                memory.status = "confirmed"
                memory.confidence = 1.0
                session.commit()
                card_text, keyboard = memory_card(memory)
                await callback.message.edit_text(card_text, reply_markup=keyboard)
                await callback.answer("Memory confirmed")
                return
        await callback.answer("Nothing changed")

    @router.callback_query(F.data.startswith("planning:"))
    async def planning_callback(callback: CallbackQuery) -> None:
        if (
            callback.from_user.id != settings.telegram_owner_id
            or callback.message is None
            or not isinstance(callback.message, TelegramMessage)
        ):
            await callback.answer()
            return
        parts = (callback.data or "").split(":", 3)
        if len(parts) != 4 or parts[1] != "delete":
            await callback.answer("Nothing changed")
            return
        _, _, entity_type, entity_id = parts
        with sessions() as session:
            user = get_or_create_user(session, callback.from_user.id, settings.user_name)
            name = delete_planning_record(session, user, entity_type, entity_id)
        if name is None:
            await callback.answer("Record not found", show_alert=True)
            return
        try:
            await callback.message.edit_text(
                f"🗑️ Deleted {entity_type}\n\n{name}", reply_markup=None
            )
        except Exception:
            pass
        await callback.answer(f"{entity_type.capitalize()} deleted")

    @router.message()
    async def chat(message: TelegramMessage) -> None:
        if message.from_user is None or message.from_user.id != settings.telegram_owner_id:
            return
        if not message.text and message.voice is None:
            await message.answer(
                "I can process text messages right now. Voice messages and other media support "
                "will be added soon."
            )
            return
        owner_id = message.from_user.id
        if is_paused(settings):
            await message.answer("I am paused for now. I will be back soon.")
            return
        if model_client is None and message.voice is not None:
            await message.answer("I need an OpenAI API key to transcribe voice messages.")
            return
        try:
            if message.voice is not None:
                assert model_client is not None
                inbound = await with_typing(
                    message, transcribe_voice(message, model_client, settings)
                )
            else:
                inbound = InboundMessage(
                    text=message.text or "",
                    source_type="telegram_text",
                    provider_message_id=message.message_id,
                )
            await send_typing(message)
        except (RuntimeError, ValueError) as exc:
            await message.answer(f"I could not process that voice message. {exc}")
            return
        if len(inbound.attachments) > settings.max_attachments:
            await message.answer("I can process only a small number of attachments at a time.")
            cleanup_inbound_attachments(inbound)
            return
        transcription_snapshot = (
            dict(model_client.last_transcription_snapshot)
            if model_client is not None and inbound.source_type == "telegram_voice"
            else {}
        )
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id, settings.user_name)
            old_cards = pending_deleted_cards(session, user, message.chat.id)
        for old_card in old_cards:
            bot = message.bot
            if bot is None:
                break
            try:
                await bot.delete_message(message.chat.id, old_card.telegram_message_id)
            except Exception:
                continue
            with sessions() as session:
                mark_card_cleaned(session, old_card.id)
        query_vector = None
        if model_client is not None:
            try:
                query_vector = await with_typing(
                    message, model_client.embed(inbound.text, settings.openai_embedding_model)
                )
            except Exception:
                pass
        user_message_id: str | None = None
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id, settings.user_name)
            conversation = get_or_create_conversation(session, user)
            user_message = add_message(
                session, conversation, "user", inbound.text, message.message_id
            )
            user_message_id = user_message.id
            save_message_attachments(session, user_message.id, inbound.attachments)
            if transcription_snapshot:
                transcription_run = create_agent_run(
                    session,
                    conversation,
                    str(transcription_snapshot.get("model", settings.openai_transcription_model)),
                    json.dumps(
                        {
                            "type": "audio_transcription",
                            "source_type": inbound.source_type,
                            "attachments": [
                                {
                                    "filename": attachment.filename,
                                    "content_type": attachment.content_type,
                                    "provider_file_id": attachment.provider_file_id,
                                    "expires_at": attachment.expires_at.isoformat(),
                                }
                                for attachment in inbound.attachments
                            ],
                            "audio_bytes": transcription_snapshot.get("audio_bytes"),
                            "audio_retained": False,
                        },
                        ensure_ascii=False,
                    ),
                )
                finish_agent_run(
                    session,
                    transcription_run.id,
                    "completed" if "error" not in transcription_snapshot else "failed",
                    transcription_snapshot.get("latency_ms"),
                    error=transcription_snapshot.get("error"),
                    response_snapshot=json.dumps(
                        transcription_snapshot.get("response", {}), ensure_ascii=False
                    ),
                )
            results = retrieve_memories(session, user, inbound.text, query_vector=query_vector)
            log_retrieval(session, user, conversation, retrieval_query(inbound.text, user), results)
            summary = get_or_create_summary(session, conversation)
            pending_state = get_open_pending_state(session, user, conversation)
            places, ideas, events, reminders = planning_context(session, user)
            summary_start = 0
            if summary.summarized_through_message_id:
                for index, item in enumerate(conversation.messages):
                    if item.id == summary.summarized_through_message_id:
                        summary_start = index + 1
                        break
            old_messages = conversation.messages[summary_start : -settings.recent_message_limit]
            summary_needed = len(conversation.messages) > settings.summary_threshold
            existing_summary = summary.summary_text
            summary_message_ids = [item.id for item in old_messages]
            summary_through_id = old_messages[-1].id if old_messages else None
        if model_client is not None and summary_needed and old_messages:
            summary_started = perf_counter()
            summary_request = json.dumps(
                {
                    "type": "rolling_summary",
                    "existing_summary": existing_summary,
                    "messages": [(item.sender, item.text) for item in old_messages],
                },
                sort_keys=True,
            )
            with sessions() as session:
                user = get_or_create_user(session, owner_id)
                conversation = get_or_create_conversation(session, user)
                summary_run = create_agent_run(
                    session,
                    conversation,
                    model_client.summary_model,
                    summary_request,
                )
            try:
                new_summary = await with_typing(
                    message,
                    model_client.summarize(
                        existing_summary,
                        [(item.sender, item.text) for item in old_messages],
                    ),
                )
                with sessions() as session:
                    user = get_or_create_user(session, message.from_user.id)
                    conversation = get_or_create_conversation(session, user)
                    summary = save_summary(
                        session,
                        conversation,
                        new_summary,
                        summary_message_ids,
                        summary_through_id,
                    )
                    finish_agent_run(
                        session,
                        summary_run.id,
                        "completed",
                        round((perf_counter() - summary_started) * 1000),
                        response_snapshot=new_summary,
                        input_tokens=model_client.last_usage[0],
                        output_tokens=model_client.last_usage[1],
                    )
            except Exception as exc:
                with sessions() as session:
                    finish_agent_run(
                        session,
                        summary_run.id,
                        "failed",
                        round((perf_counter() - summary_started) * 1000),
                        str(exc),
                        input_tokens=model_client.last_usage[0],
                        output_tokens=model_client.last_usage[1],
                    )
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id)
            conversation = get_or_create_conversation(session, user)
            summary = get_or_create_summary(session, conversation)
            pending_state = get_open_pending_state(session, user, conversation)
            built_context = build_context(
                user,
                conversation,
                inbound.text,
                results,
                settings.timezone,
                primary_person_name=settings.primary_person_name,
                summary=summary,
                pending_state=pending_state,
                places=places,
                ideas=ideas,
                events=events,
                reminders=reminders,
                prompt_text=load_prompt(settings),
                max_messages=settings.recent_message_limit,
                token_budget=settings.context_token_budget,
            )
            history = built_context.messages
        if model_client is None:
            await message.answer("I am connected, but the OpenAI API key is not configured yet.")
            return
        request_snapshot = json.dumps(
            {
                "system_prompt": built_context.static_context,
                "user_prompt": inbound.text,
                "context_added": built_context.dynamic_context,
                "recent_messages": history,
                "estimated_context_tokens": built_context.estimated_tokens,
                "tools_available": [tool["name"] for tool in AVAILABLE_TOOLS],
            },
            sort_keys=True,
        )
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id)
            conversation = get_or_create_conversation(session, user)
            run = create_agent_run(session, conversation, model_client.model, request_snapshot)
        started = perf_counter()

        def execute_model_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            with sessions() as session:
                user = get_or_create_user(session, owner_id)
                conversation = get_or_create_conversation(session, user)
                executor = MemoryToolExecutor(
                    session,
                    user,
                    agent_run_id=run.id,
                    conversation=conversation,
                    source_message_id=user_message_id,
                )
                return executor.execute(name, arguments)

        try:
            answer = await with_typing(
                message,
                model_client.reply(
                    history,
                    settings.user_name,
                    settings.primary_person_name,
                    built_context.static_context,
                    built_context.dynamic_context,
                    tool_executor=execute_model_tool,
                ),
            )
        except Exception as exc:
            with sessions() as session:
                finish_agent_run(
                    session,
                    run.id,
                    "failed",
                    round((perf_counter() - started) * 1000),
                    str(exc),
                    input_tokens=model_client.last_usage[0],
                    output_tokens=model_client.last_usage[1],
                )
            await message.answer("I ran into a problem while replying. Please try again.")
            cleanup_inbound_attachments(inbound)
            return
        with sessions() as session:
            finish_agent_run(
                session,
                run.id,
                "completed",
                round((perf_counter() - started) * 1000),
                response_snapshot=json.dumps(
                    {
                        "answer": answer,
                        "tool_calls": model_client.last_tool_trace,
                        "context_usage": retrieval_context_usage(results, answer),
                    },
                    ensure_ascii=False,
                ),
                request_snapshot=json.dumps(model_client.last_request_snapshot, ensure_ascii=False),
                input_tokens=model_client.last_usage[0],
                output_tokens=model_client.last_usage[1],
            )
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id)
            conversation = get_or_create_conversation(session, user)
            add_message(session, conversation, "assistant", answer)
        await message.answer(answer)

        published_memory_ids: set[str] = set()
        for trace in model_client.last_tool_trace:
            if trace.get("name") != "create_memory":
                continue
            output = trace.get("output", {})
            if not isinstance(output, dict) or not output.get("ok"):
                continue
            result = output.get("result", {})
            if not isinstance(result, dict):
                continue
            memory_id = result.get("memory_id")
            if not isinstance(memory_id, str) or memory_id in published_memory_ids:
                continue
            published_memory_ids.add(memory_id)
            if model_client is not None:
                try:
                    with sessions() as session:
                        user = get_or_create_user(session, owner_id)
                        memory = get_owned_memory(session, user, memory_id)
                        statement = memory.statement if memory is not None else ""
                    if statement:
                        vector = await model_client.embed(
                            statement, settings.openai_embedding_model
                        )
                        with sessions() as session:
                            user = get_or_create_user(session, owner_id)
                            set_memory_embedding(session, user, memory_id, vector)
                except Exception:
                    pass
            with sessions() as session:
                user = get_or_create_user(session, owner_id)
                memory = get_owned_memory(session, user, memory_id)
                if memory is None or memory.status == "deleted":
                    continue
                card_text, keyboard = memory_card(memory)
            card = await message.answer(card_text, reply_markup=keyboard)
            with sessions() as session:
                user = get_or_create_user(session, owner_id)
                memory = get_owned_memory(session, user, memory_id)
                if memory is not None:
                    save_telegram_card(session, memory, message.chat.id, card.message_id)

        planning_tools = {
            "create_place": ("place", "place_id"),
            "create_saved_idea": ("idea", "idea_id"),
            "create_event": ("event", "event_id"),
            "create_reminder": ("reminder", "reminder_id"),
        }
        published_planning_ids: set[tuple[str, str]] = set()
        for trace in model_client.last_tool_trace:
            tool_name = trace.get("name")
            if not isinstance(tool_name, str):
                continue
            tool_info = planning_tools.get(tool_name)
            if tool_info is None:
                continue
            output = trace.get("output", {})
            if not isinstance(output, dict) or not output.get("ok"):
                continue
            result = output.get("result", {})
            if not isinstance(result, dict):
                continue
            entity_type, id_key = tool_info
            entity_id = result.get(id_key)
            if not isinstance(entity_id, str):
                continue
            identity = (entity_type, entity_id)
            if identity in published_planning_ids:
                continue
            published_planning_ids.add(identity)
            with sessions() as session:
                user = get_or_create_user(session, owner_id, settings.user_name)
                record = get_owned_planning_record(session, user, entity_type, entity_id)
                if record is None or record.status in {
                    "deleted",
                    "cancelled",
                }:
                    continue
                card_text, keyboard = planning_card(entity_type, record)
            card = await message.answer(card_text, reply_markup=keyboard)
            with sessions() as session:
                user = get_or_create_user(session, owner_id, settings.user_name)
                record = get_owned_planning_record(session, user, entity_type, entity_id)
                if record is not None:
                    save_telegram_planning_card(
                        session,
                        user,
                        entity_type,
                        entity_id,
                        message.chat.id,
                        card.message_id,
                    )
        cleanup_inbound_attachments(inbound)

    dispatcher.include_router(router)
    return dispatcher


async def run_bot(settings: Settings) -> None:
    if not settings.telegram_bot_token or settings.telegram_owner_id is None:
        raise RuntimeError("Telegram bot token and owner ID are required")
    bot = Bot(settings.telegram_bot_token)
    try:
        await build_dispatcher(settings).start_polling(bot)
    finally:
        await bot.session.close()
