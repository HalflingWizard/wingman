"""Application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openai_main_model: str = "gpt-4o-mini"
    openai_summary_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    summary_threshold: int = Field(default=40, ge=10, le=500)
    recent_message_limit: int = Field(default=20, ge=5, le=100)
    context_token_budget: int = Field(default=4000, ge=500, le=16000)
    user_name: str = ""
    primary_person_name: str = ""
    timezone: str = "UTC"
    data_dir: str = "./data"
    log_dir: str = "./logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
