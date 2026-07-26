"""Safe export, backup, and update helpers."""

import json
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


def repository_version() -> dict[str, str]:
    """Return the loaded source revision without failing when Git is unavailable."""
    root = Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        message = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unavailable", "message": "Git metadata unavailable", "branch": ""}
    return {"commit": commit, "message": message, "branch": branch}


def _update_status_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "update_status.json"


def write_update_status(
    settings: Settings,
    status: str,
    logs: list[str],
    error: str = "",
    branch: str = "",
) -> None:
    path = _update_status_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"status": status, "logs": logs[-200:], "error": error, "branch": branch},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def read_update_status(settings: Settings) -> dict[str, Any]:
    try:
        value = json.loads(_update_status_path(settings).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "idle", "logs": [], "error": "", "branch": ""}
    return value if isinstance(value, dict) else {"status": "idle", "logs": []}


def ensure_media_tools(settings: Settings, logs: list[str]) -> None:
    """Install FFmpeg when the local package manager is available."""
    if all(
        Path(candidate).is_file()
        for candidate in (
            shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg",
            shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe",
        )
    ):
        logs.append("FFmpeg and ffprobe are available")
        return
    brew = shutil.which("brew")
    if brew is None:
        raise RuntimeError("FFmpeg is required for video processing. Install it with Homebrew")
    logs.append("FFmpeg is missing. Installing it with Homebrew")
    result = subprocess.run(
        [brew, "install", "ffmpeg"], cwd=Path(__file__).resolve().parent.parent, check=False
    )
    if result.returncode != 0:
        raise RuntimeError("Homebrew could not install FFmpeg")
    logs.append("FFmpeg installation completed")


def database_diagnostics(settings: Settings, session: Session, user: User) -> dict[str, object]:
    """Return safe database and owner-scope information for local diagnostics."""
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        resolved_path = database_path.resolve()
        exists = resolved_path.exists()
        size = resolved_path.stat().st_size if exists else 0
    else:
        resolved_path = None
        exists = True
        size = None
    return {
        "database_url": settings.database_url,
        "database_path": str(resolved_path) if resolved_path is not None else None,
        "database_exists": exists,
        "database_size_bytes": size,
        "configured_owner_id": settings.telegram_owner_id,
        "database_user_id": user.id,
        "database_telegram_user_id": user.telegram_user_id,
        "database_user_name": user.name,
        "memory_count": session.query(Memory).filter_by(user_id=user.id).count(),
        "place_count": session.query(Place).filter_by(user_id=user.id).count(),
        "idea_count": session.query(SavedIdea).filter_by(user_id=user.id).count(),
        "event_count": session.query(Event).filter_by(user_id=user.id).count(),
        "reminder_count": session.query(Reminder).filter_by(user_id=user.id).count(),
    }


def _row(record: Any, fields: list[str]) -> dict[str, object]:
    return {field: getattr(record, field) for field in fields}


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value))


def _restore_row(
    session: Session, model: type[Any], payload: dict[str, object], fields: list[str]
) -> Any:
    identifier = payload.get("id")
    record = session.get(model, identifier) if identifier else None
    if record is None:
        record = model(id=str(identifier)) if identifier else model()
        session.add(record)
    for field in fields:
        if field in payload:
            value = payload[field]
            if field.endswith("_at") or field in {"created_at", "updated_at"}:
                value = _parse_datetime(value)
            setattr(record, field, value)
    return record


def import_user_data(session: Session, user: User, payload: object) -> None:
    """Restore an export while keeping all imported records owned by this user."""
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported Wingman export")
    for item in payload.get("conversations", []):
        if isinstance(item, dict):
            _restore_row(
                session,
                Conversation,
                {**item, "user_id": user.id},
                ["user_id", "created_at"],
            )
    session.flush()
    for item in payload.get("messages", []):
        if isinstance(item, dict):
            _restore_row(
                session,
                Message,
                item,
                ["conversation_id", "sender", "text", "telegram_message_id", "created_at"],
            )
    for item in payload.get("memories", []):
        if isinstance(item, dict):
            _restore_row(
                session,
                Memory,
                {**item, "user_id": user.id},
                [
                    "user_id",
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
    session.flush()
    for item in payload.get("memory_notes", []):
        if isinstance(item, dict):
            _restore_row(
                session,
                MemoryNote,
                item,
                ["memory_id", "text", "note_type", "source_message_id", "confidence", "created_at"],
            )
    collections = (
        ("places", Place, ["name", "place_type", "address", "city", "description", "status"]),
        ("ideas", SavedIdea, ["title", "reason", "place_id", "status", "used"]),
        ("events", Event, ["title", "event_type", "start_at", "end_at", "status", "description"]),
        ("reminders", Reminder, ["title", "scheduled_at", "timezone", "status", "delivery_status"]),
    )
    for key, model, fields in collections:
        for item in payload.get(key, []):
            if isinstance(item, dict):
                _restore_row(session, model, {**item, "user_id": user.id}, ["user_id", *fields])
    for item in payload.get("summaries", []):
        if isinstance(item, dict):
            _restore_row(
                session,
                ConversationSummary,
                item,
                [
                    "conversation_id",
                    "summary_text",
                    "summarized_through_message_id",
                    "estimated_tokens",
                    "updated_at",
                ],
            )
    session.commit()


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
    root = Path(__file__).resolve().parent.parent
    logs: list[str] = []
    write_update_status(settings, "running", ["Checking the working tree"])
    clean = subprocess.run(["git", "diff", "--quiet"], cwd=root, check=False)
    if clean.returncode != 0:
        write_update_status(
            settings,
            "failed",
            ["Working tree has uncommitted changes"],
            "Refusing update",
        )
        raise RuntimeError("Refusing update because the working tree has uncommitted changes")
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    logs.append(f"Updating branch {branch}")
    write_update_status(settings, "running", logs, branch=branch)
    try:
        pull = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=root, check=True, capture_output=True, text=True
        )
        logs.extend(line for line in pull.stdout.splitlines() if line.strip())
        logs.append("Installing the current project and development dependencies")
        write_update_status(settings, "running", logs, branch=branch)
        install = subprocess.run(
            [".venv/bin/python", "-m", "pip", "install", "-qqq", "-e", ".[dev]"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        logs.extend(line for line in install.stdout.splitlines() if line.strip())
        ensure_media_tools(settings, logs)
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        logs.extend(line for line in output.splitlines() if line.strip())
        write_update_status(settings, "failed", logs, str(exc), branch)
        raise
    write_update_status(settings, "completed", logs + ["Update completed"], branch=branch)
    return branch
