"""Small local bot lifecycle state store."""

import json
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
