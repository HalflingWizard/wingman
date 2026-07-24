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
    user_name: str = ""
    primary_person_name: str = ""
    timezone: str = "UTC"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
