"""Small local bot lifecycle state store."""

import json
import os
import signal
import sys
import threading
from pathlib import Path

from wingman.config import Settings


def _path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "bot_state.json"


def is_paused(settings: Settings) -> bool:
    try:
        return bool(json.loads(_path(settings).read_text(encoding="utf-8")).get("paused"))
    except (OSError, json.JSONDecodeError):
        return False


def set_paused(settings: Settings, paused: bool) -> None:
    path = _path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paused": paused}), encoding="utf-8")
    path.chmod(0o600)


def restart_process(no_browser: bool = True, delay_seconds: float = 0.0) -> None:
    """Restart cleanly, allowing systemd to create a fresh polling session."""
    command = [sys.executable, "-m", "wingman.cli", "start"]
    if no_browser:
        command.append("--no-browser")

    def replace() -> None:
        if os.environ.get("INVOCATION_ID"):
            # A system service must be restarted by its supervisor. The service
            # unit should use Restart=always, so SIGTERM produces a clean stop
            # and a new process without a second Telegram poller.
            os.kill(os.getpid(), signal.SIGTERM)
            return
        os.execv(sys.executable, command)

    if delay_seconds > 0:
        threading.Timer(delay_seconds, replace).start()
    else:
        replace()


def schedule_restart(no_browser: bool = True, delay_seconds: float = 1.0) -> None:
    """Restart shortly after an HTTP response has been returned to the browser."""
    thread = threading.Thread(
        target=restart_process,
        kwargs={"no_browser": no_browser, "delay_seconds": delay_seconds},
        daemon=True,
    )
    thread.start()
