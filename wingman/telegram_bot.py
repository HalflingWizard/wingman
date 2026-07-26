"""Telegram polling and owner authorization."""

import asyncio
import json
import shutil
from collections.abc import Awaitable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
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
    action_ledger,
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

SUPPORTED_DOCUMENTS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
}
SUPPORTED_VIDEOS = {".mp4", ".mov", ".m4v", ".webm"}
VIDEO_FRAME_COUNT = 5


def supported_document_type(filename: str, mime_type: str | None = None) -> str | None:
    extension = Path(filename).suffix.casefold()
    if extension not in SUPPORTED_DOCUMENTS:
        return None
    return mime_type or SUPPORTED_DOCUMENTS[extension]


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


async def download_photos(messages: list[TelegramMessage], settings: Settings) -> InboundMessage:
    if not messages or any(not message.photo or message.bot is None for message in messages):
        raise ValueError("Image message is not available")
    if len(messages) > settings.max_attachments:
        raise ValueError(f"I can process at most {settings.max_attachments} images at a time")
    attachments: list[InboundAttachment] = []
    total_bytes = 0
    try:
        for message in messages:
            if message.photo is None or message.bot is None:
                raise ValueError("Image message is not available")
            photo = message.photo[-1]
            if photo.file_size and photo.file_size > settings.image_max_bytes:
                raise ValueError("Image is too large")
            remote_file = await message.bot.get_file(photo.file_id)
            if not remote_file.file_path:
                raise RuntimeError("Telegram did not provide an image file path")
            buffer = BytesIO()
            try:
                await message.bot.download_file(remote_file.file_path, destination=buffer)
                image = buffer.getvalue()
            finally:
                buffer.close()
            if len(image) > settings.image_max_bytes:
                raise ValueError("Image is too large")
            total_bytes += len(image)
            if total_bytes > settings.image_total_max_bytes:
                raise ValueError("The combined image size is too large")
            with NamedTemporaryFile(prefix="wingman-image-", suffix=".jpg", delete=False) as file:
                file.write(image)
                local_path = file.name
            attachments.append(
                InboundAttachment(
                    source_type="telegram_image",
                    provider_file_id=photo.file_id,
                    filename="wingman-image.jpg",
                    content_type="image/jpeg",
                    local_path=local_path,
                    size_bytes=len(image),
                    width=photo.width,
                    height=photo.height,
                    expires_at=datetime.now(UTC)
                    + timedelta(seconds=settings.attachment_retention_seconds),
                )
            )
    except Exception:
        cleanup_inbound_attachments(InboundMessage("", attachments=tuple(attachments)))
        raise
    return InboundMessage(
        text=next((message.caption or "" for message in messages if message.caption), ""),
        source_type="telegram_image",
        provider_message_id=messages[0].message_id,
        attachments=tuple(attachments),
    )


async def download_photo(message: TelegramMessage, settings: Settings) -> InboundMessage:
    return await download_photos([message], settings)


async def download_image_document(message: TelegramMessage, settings: Settings) -> InboundMessage:
    document = message.document
    if document is None or message.bot is None:
        raise ValueError("Image document is not available")
    content_type = document.mime_type or ""
    filename = document.file_name or "wingman-image"
    if not content_type.casefold().startswith("image/"):
        raise ValueError(
            "This file type is not supported yet. I can currently process text, voice, and images."
        )
    if document.file_size and document.file_size > settings.image_max_bytes:
        raise ValueError("Image is too large")
    remote_file = await message.bot.get_file(document.file_id)
    if not remote_file.file_path:
        raise RuntimeError("Telegram did not provide an image file path")
    buffer = BytesIO()
    local_path = ""
    try:
        await message.bot.download_file(remote_file.file_path, destination=buffer)
        image = buffer.getvalue()
        if len(image) > settings.image_max_bytes:
            raise ValueError("Image is too large")
        with NamedTemporaryFile(prefix="wingman-image-", suffix=".bin", delete=False) as file:
            file.write(image)
            local_path = file.name
    except Exception:
        if local_path:
            cleanup_inbound_attachments(
                InboundMessage(
                    "",
                    attachments=(
                        InboundAttachment(
                            "telegram_image", document.file_id, local_path=local_path
                        ),
                    ),
                )
            )
        raise
    finally:
        buffer.close()
    return InboundMessage(
        text=message.caption or "",
        source_type="telegram_image",
        provider_message_id=message.message_id,
        attachments=(
            InboundAttachment(
                source_type="telegram_image",
                provider_file_id=document.file_id,
                filename=filename,
                content_type=content_type,
                local_path=local_path,
                size_bytes=len(image),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.attachment_retention_seconds),
            ),
        ),
    )


async def download_document(message: TelegramMessage, settings: Settings) -> InboundMessage:
    document = message.document
    if document is None or message.bot is None:
        raise ValueError("Document is not available")
    filename = document.file_name or "wingman-document"
    extension = Path(filename).suffix.casefold()
    content_type = supported_document_type(filename, document.mime_type)
    if content_type is None:
        raise ValueError(
            "This file type is not supported yet. Supported files are PDF, DOCX, TXT, "
            "Markdown, CSV, and JSON."
        )
    if document.file_size and document.file_size > settings.document_max_bytes:
        raise ValueError("Document is too large")
    remote_file = await message.bot.get_file(document.file_id)
    if not remote_file.file_path:
        raise RuntimeError("Telegram did not provide a document file path")
    buffer = BytesIO()
    local_path = ""
    try:
        await asyncio.wait_for(
            message.bot.download_file(remote_file.file_path, destination=buffer),
            timeout=settings.document_processing_timeout_seconds,
        )
        document_bytes = buffer.getvalue()
        if len(document_bytes) > settings.document_max_bytes:
            raise ValueError("Document is too large")
        estimated_characters = None
        if extension in {".txt", ".md", ".markdown", ".csv", ".json"}:
            try:
                estimated_characters = len(document_bytes.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise ValueError("Text documents must use UTF-8 encoding") from exc
            if estimated_characters > settings.document_max_characters:
                raise ValueError("Text document is too long")
        with NamedTemporaryFile(prefix="wingman-document-", suffix=extension, delete=False) as file:
            file.write(document_bytes)
            local_path = file.name
    except Exception:
        if local_path:
            cleanup_inbound_attachments(
                InboundMessage(
                    "",
                    attachments=(
                        InboundAttachment(
                            "telegram_document", document.file_id, local_path=local_path
                        ),
                    ),
                )
            )
        raise
    finally:
        buffer.close()
    return InboundMessage(
        text=message.caption or "",
        source_type="telegram_document",
        provider_message_id=message.message_id,
        attachments=(
            InboundAttachment(
                source_type="telegram_document",
                provider_file_id=document.file_id,
                filename=filename,
                content_type=content_type,
                local_path=local_path,
                size_bytes=len(document_bytes),
                estimated_characters=estimated_characters,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.attachment_retention_seconds),
            ),
        ),
    )


async def run_media_command(command: list[str], timeout_seconds: int) -> tuple[bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError("Video processing timed out") from exc
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
        raise RuntimeError(detail[0] if detail else "Video processing failed")
    return stdout, stderr


async def inspect_video(path: str, settings: Settings) -> tuple[float, bool]:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("Video processing tools are not installed")
    stdout, _ = await run_media_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            path,
        ],
        settings.video_processing_timeout_seconds,
    )
    try:
        metadata = json.loads(stdout.decode("utf-8"))
        duration = float(metadata["format"]["duration"])
        stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not read video metadata") from exc
    if duration <= 0:
        raise ValueError("Video duration is invalid")
    if duration > settings.video_max_duration_seconds:
        raise ValueError("Video is too long")
    return duration, "audio" in stream_types


async def download_video(
    message: TelegramMessage, model_client: ModelClient, settings: Settings
) -> InboundMessage:
    video = message.video
    if video is None or message.bot is None:
        raise ValueError("Video message is not available")
    filename = video.file_name or "wingman-video.mp4"
    extension = Path(filename).suffix.casefold() or ".mp4"
    if extension not in SUPPORTED_VIDEOS:
        raise ValueError("This video format is not supported yet")
    if video.file_size and video.file_size > settings.video_max_bytes:
        raise ValueError("Video is too large")
    remote_file = await message.bot.get_file(video.file_id)
    if not remote_file.file_path:
        raise RuntimeError("Telegram did not provide a video file path")
    video_path = ""
    audio_path = ""
    frame_paths: list[str] = []
    try:
        with NamedTemporaryFile(prefix="wingman-video-", suffix=extension, delete=False) as file:
            video_path = file.name
        with open(video_path, "wb") as file:
            await asyncio.wait_for(
                message.bot.download_file(remote_file.file_path, destination=file),
                timeout=settings.video_processing_timeout_seconds,
            )
        if Path(video_path).stat().st_size > settings.video_max_bytes:
            raise ValueError("Video is too large")
        duration, has_audio = await inspect_video(video_path, settings)
        transcript = ""
        if has_audio:
            with NamedTemporaryFile(
                prefix="wingman-video-audio-", suffix=".ogg", delete=False
            ) as file:
                audio_path = file.name
            await run_media_command(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "libopus",
                    audio_path,
                ],
                settings.video_processing_timeout_seconds,
            )
            transcript = await model_client.transcribe(
                Path(audio_path).read_bytes(),
                "wingman-video-audio.ogg",
                settings.openai_transcription_model,
            )
        for index in range(VIDEO_FRAME_COUNT):
            timestamp = duration * index / (VIDEO_FRAME_COUNT - 1)
            with NamedTemporaryFile(
                prefix=f"wingman-video-frame-{index + 1}-", suffix=".jpg", delete=False
            ) as file:
                frame_path = file.name
            await run_media_command(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    frame_path,
                ],
                settings.video_processing_timeout_seconds,
            )
            frame_paths.append(frame_path)
        text = message.caption or ""
        if transcript:
            text = f"{text}\n\n[Video transcript]\n{transcript}".strip()
        attachments = tuple(
            InboundAttachment(
                source_type="telegram_video_frame",
                provider_file_id=video.file_id,
                filename=f"{Path(filename).stem}-frame-{index + 1}.jpg",
                content_type="image/jpeg",
                local_path=frame_path,
                size_bytes=Path(frame_path).stat().st_size,
                duration_seconds=duration,
                frame_index=index + 1,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.attachment_retention_seconds),
            )
            for index, frame_path in enumerate(frame_paths)
        )
        frame_paths = []
        return InboundMessage(
            text=text,
            source_type="telegram_video",
            provider_message_id=message.message_id,
            attachments=attachments,
        )
    finally:
        for path in [video_path, audio_path, *frame_paths]:
            if path:
                Path(path).unlink(missing_ok=True)


def build_dispatcher(settings: Settings) -> Dispatcher:
    dispatcher = Dispatcher()
    router = Router()
    sessions = session_factory(settings)
    model_client = ModelClient(settings) if settings.openai_api_key else None
    image_groups: dict[str, list[TelegramMessage]] = {}

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
        if (
            not message.text
            and message.voice is None
            and not message.photo
            and not message.document
            and message.video is None
        ):
            await message.answer(
                "I can process text, voice, image, document, and video messages. "
                "This message type is not supported yet."
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
            elif message.photo:
                if model_client is None:
                    await message.answer("I need an OpenAI API key to analyze images.")
                    return
                if message.media_group_id:
                    group_id = message.media_group_id
                    if group_id in image_groups:
                        image_groups[group_id].append(message)
                        return
                    image_groups[group_id] = [message]
                    await asyncio.sleep(0.35)
                    grouped_messages = image_groups.pop(group_id, [])
                    inbound = await with_typing(
                        message, download_photos(grouped_messages, settings)
                    )
                else:
                    inbound = await with_typing(message, download_photo(message, settings))
            elif message.document:
                if model_client is None:
                    await message.answer("I need an OpenAI API key to analyze files.")
                    return
                if (message.document.mime_type or "").casefold().startswith("image/"):
                    inbound = await with_typing(message, download_image_document(message, settings))
                else:
                    inbound = await with_typing(message, download_document(message, settings))
            elif message.video is not None:
                if model_client is None:
                    await message.answer("I need an OpenAI API key to analyze videos.")
                    return
                inbound = await with_typing(
                    message, download_video(message, model_client, settings)
                )
            else:
                inbound = InboundMessage(
                    text=message.text or "",
                    source_type="telegram_text",
                    provider_message_id=message.message_id,
                )
            await send_typing(message)
        except (RuntimeError, ValueError) as exc:
            await message.answer(f"I could not process that input. {exc}")
            return
        if len(inbound.attachments) > settings.max_attachments:
            await message.answer("I can process only a small number of attachments at a time.")
            cleanup_inbound_attachments(inbound)
            return
        transcription_snapshot = (
            dict(model_client.last_transcription_snapshot)
            if model_client is not None
            and inbound.source_type in {"telegram_voice", "telegram_video"}
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
                if inbound.text.strip():
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
            current_action_ledger = action_ledger(session, user, conversation)
            built_context = build_context(
                user,
                conversation,
                inbound.text,
                results,
                settings.timezone,
                primary_person_name=settings.primary_person_name,
                summary=summary,
                pending_state=pending_state,
                action_ledger=current_action_ledger,
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
            cleanup_inbound_attachments(inbound)
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
                    attachments=inbound.attachments,
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
            if result.get("verified") is not True:
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
            if result.get("verified") is not True:
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
