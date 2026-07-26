"""Bounded in-process runtime output for the local dashboard."""

from collections import deque
from datetime import UTC, datetime
from threading import Lock

MAX_RUNTIME_LINES = 100
_lock = Lock()
_lines: deque[dict[str, str]] = deque(maxlen=MAX_RUNTIME_LINES)


def record_runtime_output(message: str, *, level: str = "info", operation: str = "runtime") -> None:
    """Keep a short, safe operational line without raw request or media data."""
    clean_message = " ".join(str(message).split())[:500]
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level.casefold() if level else "info",
        "operation": operation[:80],
        "message": clean_message,
    }
    with _lock:
        _lines.append(entry)


def recent_runtime_output(limit: int = MAX_RUNTIME_LINES) -> list[dict[str, str]]:
    """Return the newest bounded runtime lines in chronological order."""
    safe_limit = max(1, min(limit, MAX_RUNTIME_LINES))
    with _lock:
        return list(_lines)[-safe_limit:]
