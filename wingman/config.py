"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EDITABLE_SETTINGS = {
    "telegram_bot_token": "WINGMAN_TELEGRAM_BOT_TOKEN",
    "telegram_owner_id": "WINGMAN_TELEGRAM_OWNER_ID",
    "openai_api_key": "WINGMAN_OPENAI_API_KEY",
    "openai_main_model": "WINGMAN_OPENAI_MAIN_MODEL",
    "openai_summary_model": "WINGMAN_OPENAI_SUMMARY_MODEL",
    "user_name": "WINGMAN_USER_NAME",
    "primary_person_name": "WINGMAN_PRIMARY_PERSON_NAME",
    "timezone": "WINGMAN_TIMEZONE",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WINGMAN_",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str = "sqlite:///./wingman.db"
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8080, ge=1, le=65535)
    telegram_bot_token: str = ""
    telegram_owner_id: int | None = Field(default=None, ge=1)
    openai_api_key: str = ""
    openai_main_model: str = "gpt-5-nano"
    openai_summary_model: str = "gpt-5-nano"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    voice_max_bytes: int = Field(default=25_000_000, ge=1_000_000, le=25_000_000)
    max_attachments: int = Field(default=5, ge=1, le=10)
    attachment_retention_seconds: int = Field(default=600, ge=60, le=3600)
    summary_threshold: int = Field(default=40, ge=10, le=500)
    recent_message_limit: int = Field(default=20, ge=5, le=100)
    context_token_budget: int = Field(default=4000, ge=500, le=16000)
    user_name: str = ""
    primary_person_name: str = ""
    timezone: str = "UTC"
    prompt_file: str = "prompts/wingman.md"
    data_dir: str = "./data"
    log_dir: str = "./logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def save_runtime_settings(settings: Settings, values: dict[str, str]) -> None:
    """Apply dashboard settings and persist them in the local env file."""
    env_path = Settings.model_config.get("env_file", ".env")
    path = Path(str(env_path))
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value
    for field, env_key in EDITABLE_SETTINGS.items():
        value = values.get(field, "")
        if field in {"telegram_bot_token", "openai_api_key"} and not value:
            value = str(getattr(settings, field))
        if field == "telegram_owner_id" and value:
            setattr(settings, field, int(value))
        elif value:
            setattr(settings, field, value)
        existing[env_key] = value
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in existing.items()) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
