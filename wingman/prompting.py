"""Load owner-editable conversation guidance."""

from pathlib import Path

from wingman.config import Settings

DEFAULT_PROMPT = (
    "Be warm, natural, concise, and attentive. Use the owner's name when it feels natural. "
    "Explain suggestions in ordinary language and stay active when several useful actions "
    "are possible."
)


def load_prompt(settings: Settings) -> str:
    try:
        prompt = Path(settings.prompt_file).read_text(encoding="utf-8").strip()
    except OSError:
        prompt = ""
    return prompt[:12000] or DEFAULT_PROMPT


def save_prompt(settings: Settings, prompt: str) -> None:
    path = Path(settings.prompt_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt.strip()[:12000] + "\n", encoding="utf-8")
