"""Load owner-editable conversation guidance."""

from pathlib import Path

from wingman.config import Settings

DEFAULT_PROMPT = (
    "Be warm, natural, concise, and attentive. Use the owner's name when it feels natural. "
    "Ask one useful follow-up question at a time. Explain suggestions in ordinary language."
)


def load_prompt(settings: Settings) -> str:
    try:
        prompt = Path(settings.prompt_file).read_text(encoding="utf-8").strip()
    except OSError:
        prompt = ""
    return prompt[:12000] or DEFAULT_PROMPT
