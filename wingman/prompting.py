"""Load and persist owner-editable conversation guidance."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from wingman.config import Settings

PROMPT_SECTION_LABELS = {
    "personality_safety": "Personality and safety",
    "memory_planning": "Memory and planning behavior",
    "tool_orchestration": "Tool orchestration",
    "attachment_capabilities": "Attachment capabilities",
    "custom_instructions": "Custom host instructions",
}

DEFAULT_PROMPT_SECTIONS = {
    "personality_safety": (
        "Be warm, natural, concise, and attentive. Use the owner's name when it feels natural. "
        "Keep facts, observations, and inferences separate. Do not recommend manipulation, "
        "pressure, surveillance, or deception."
    ),
    "memory_planning": (
        "Save useful durable details when they can improve future replies. Search related "
        "records before creating duplicates. Keep memories, places, ideas, events, and reminders "
        "distinct. Do not invent missing dates, times, addresses, or facts."
    ),
    "tool_orchestration": (
        "Use the available tools when saved context or a database action is relevant. Complete "
        "all safe requested actions before replying. Keep internal tool details out of the reply."
    ),
    "attachment_capabilities": (
        "Use only evidence provided by the attachment. Be honest about unclear images, files, "
        "audio, and video. Do not claim to browse, edit files, or inspect unavailable content."
    ),
    "custom_instructions": "",
}
DEFAULT_PROMPT = DEFAULT_PROMPT_SECTIONS["personality_safety"]


def _configuration_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "prompt_config.json"


def _legacy_sections(settings: Settings) -> dict[str, str]:
    sections = dict(DEFAULT_PROMPT_SECTIONS)
    try:
        legacy_text = Path(settings.prompt_file).read_text(encoding="utf-8").strip()
    except OSError:
        legacy_text = ""
    if legacy_text:
        sections["personality_safety"] = legacy_text[:6000]
    return sections


def _normalize_sections(raw: Any) -> dict[str, str]:
    sections = dict(DEFAULT_PROMPT_SECTIONS)
    if isinstance(raw, dict):
        for key in PROMPT_SECTION_LABELS:
            value = raw.get(key)
            if isinstance(value, str):
                sections[key] = value.strip()[:6000]
    return sections


def load_prompt_configuration(settings: Settings) -> dict[str, Any]:
    """Load the active prompt directly from disk without a stale process cache."""
    path = _configuration_path(settings)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "prompt_version_id": None,
            "version_number": 0,
            "updated_at": None,
            "updated_by": None,
            "active": True,
            "sections": _legacy_sections(settings),
        }
    if not isinstance(payload, dict):
        return {
            "prompt_version_id": None,
            "version_number": 0,
            "updated_at": None,
            "updated_by": None,
            "active": True,
            "sections": _legacy_sections(settings),
        }
    payload["sections"] = _normalize_sections(payload.get("sections"))
    return payload


def load_prompt_sections(settings: Settings) -> dict[str, str]:
    return cast(dict[str, str], load_prompt_configuration(settings)["sections"])


def render_prompt_sections(sections: dict[str, str]) -> str:
    parts = []
    for key, label in PROMPT_SECTION_LABELS.items():
        text = sections.get(key, "").strip()
        if text:
            parts.append(f"## {label}\n{text}")
    return "\n\n".join(parts)


def load_prompt(settings: Settings) -> str:
    return render_prompt_sections(load_prompt_sections(settings))


def save_prompt_sections(
    settings: Settings,
    sections: dict[str, str],
    updated_by: str = "dashboard",
) -> dict[str, Any]:
    normalized = _normalize_sections(sections)
    configuration = load_prompt_configuration(settings)
    version_number = int(configuration.get("version_number") or 0) + 1
    payload = {
        "prompt_version_id": str(uuid4()),
        "version_number": version_number,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": updated_by,
        "active": True,
        "sections": normalized,
    }
    path = _configuration_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    legacy_path = Path(settings.prompt_file)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(render_prompt_sections(normalized) + "\n", encoding="utf-8")
    return payload


def save_prompt(settings: Settings, prompt: str) -> None:
    sections = load_prompt_sections(settings)
    sections["personality_safety"] = prompt.strip()[:6000]
    save_prompt_sections(settings, sections)
