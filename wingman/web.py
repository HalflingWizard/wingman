"""FastAPI application."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from wingman import __version__
from wingman.config import Settings, get_settings
from wingman.database import make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="Wingman", version=__version__)

    @app.get("/health", response_class=HTMLResponse)
    def health() -> str:
        database = "ok"
        try:
            with make_engine(active_settings).connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            database = "error"
        telegram = (
            "configured"
            if active_settings.telegram_bot_token and active_settings.telegram_owner_id
            else "not configured"
        )
        openai = "configured" if active_settings.openai_api_key else "not configured"
        return (
            "<html><head><title>Wingman health</title></head><body>"
            f"<h1>Wingman {__version__}</h1><p>Database {database}</p>"
            f"<p>Telegram {telegram}</p><p>OpenAI {openai}</p>"
            "</body></html>"
        )

    return app
