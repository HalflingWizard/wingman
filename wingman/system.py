"""Safe export, backup, and update helpers."""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from wingman.config import Settings
from wingman.models import (
    Conversation,
    ConversationSummary,
    Event,
    Memory,
    MemoryNote,
    Message,
    Place,
    Reminder,
    SavedIdea,
    User,
)


def _row(record: Any, fields: list[str]) -> dict[str, object]:
    return {field: getattr(record, field) for field in fields}


def export_user_data(session: Session, user: User) -> dict[str, object]:
    conversations = list(session.query(Conversation).filter_by(user_id=user.id))
    conversation_ids = {item.id for item in conversations}
    memories = list(session.query(Memory).filter_by(user_id=user.id))
    memory_ids = {item.id for item in memories}
    return {
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": _row(user, ["id", "telegram_user_id", "name", "created_at"]),
        "conversations": [_row(item, ["id", "created_at"]) for item in conversations],
        "summaries": [
            _row(
                item,
                [
                    "id",
                    "conversation_id",
                    "summary_text",
                    "summarized_through_message_id",
                    "estimated_tokens",
                    "updated_at",
                ],
            )
            for item in session.query(ConversationSummary).filter(
                ConversationSummary.conversation_id.in_(conversation_ids)
            )
        ],
        "messages": [
            _row(item, ["id", "conversation_id", "sender", "text", "created_at"])
            for item in session.query(Message).filter(Message.conversation_id.in_(conversation_ids))
        ],
        "memories": [
            _row(
                item,
                [
                    "id",
                    "type",
                    "statement",
                    "status",
                    "confidence",
                    "importance",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                ],
            )
            for item in memories
        ],
        "memory_notes": [
            _row(item, ["id", "memory_id", "text", "note_type", "confidence", "created_at"])
            for item in session.query(MemoryNote).filter(MemoryNote.memory_id.in_(memory_ids))
        ],
        "places": [
            _row(
                item,
                ["id", "name", "place_type", "address", "city", "description", "status"],
            )
            for item in session.query(Place).filter_by(user_id=user.id)
        ],
        "ideas": [
            _row(item, ["id", "title", "reason", "place_id", "status", "used"])
            for item in session.query(SavedIdea).filter_by(user_id=user.id)
        ],
        "events": [
            _row(item, ["id", "title", "event_type", "start_at", "end_at", "status", "description"])
            for item in session.query(Event).filter_by(user_id=user.id)
        ],
        "reminders": [
            _row(item, ["id", "title", "scheduled_at", "timezone", "status", "delivery_status"])
            for item in session.query(Reminder).filter_by(user_id=user.id)
        ],
    }


def backup_database(settings: Settings) -> Path:
    source = Path(settings.database_url.removeprefix("sqlite:///"))
    backup_dir = Path(settings.data_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"wingman-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2(source, target)
    target.chmod(0o600)
    return target


def safe_update(settings: Settings) -> str:
    root = Path.cwd()
    clean = subprocess.run(["git", "diff", "--quiet"], cwd=root, check=False)
    if clean.returncode != 0:
        raise RuntimeError("Refusing update because the working tree has uncommitted changes")
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "pull", "--ff-only"], cwd=root, check=True)
    subprocess.run(
        [".venv/bin/python", "-m", "pip", "install", "-qqq", "-e", ".[dev]"],
        cwd=root,
        check=True,
    )
    return branch
