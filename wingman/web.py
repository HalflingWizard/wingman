"""FastAPI application."""

from html import escape

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wingman import __version__
from wingman.config import Settings, get_settings
from wingman.database import make_engine, session_factory
from wingman.models import User
from wingman.services import (
    confirm_memory,
    create_memory,
    delete_memory,
    list_memories,
    update_memory,
)


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

    def web_user(session: Session) -> User:
        if active_settings.telegram_owner_id is None:
            raise HTTPException(status_code=400, detail="Configure the Telegram owner ID first")
        user = session.scalar(
            select(User).where(User.telegram_user_id == active_settings.telegram_owner_id)
        )
        if user is None:
            user = User(
                telegram_user_id=active_settings.telegram_owner_id,
                name=active_settings.user_name,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user

    @app.get("/memories", response_class=HTMLResponse)
    def memories() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            records = list_memories(session, user, include_deleted=True)
        rows = []
        for memory in records:
            action = "restore" if memory.status == "deleted" else "delete"
            action_label = "Restore" if action == "restore" else "Delete"
            rows.append(
                "<article style='border:1px solid #ddd;padding:1rem;margin:1rem 0'>"
                f"<p><strong>{memory.type}</strong> {memory.status}</p>"
                f"<p>{escape(memory.statement)}</p>"
                f"<form method='post' action='/memories/{memory.id}/update'>"
                f"<input name='statement' value='{escape(memory.statement, quote=True)}' "
                "maxlength='4000' required>"
                "<button>Save</button></form>"
                f"<form method='post' action='/memories/{memory.id}/{action}' "
                "style='display:inline'>"
                f"<button>{action_label}</button></form>"
                + (
                    f"<form method='post' action='/memories/{memory.id}/confirm' "
                    "style='display:inline'>"
                    "<button>Confirm</button></form>"
                    if memory.status == "inferred"
                    else ""
                )
                + "</article>"
            )
        return (
            "<html><head><title>Wingman memories</title></head><body>"
            "<h1>Memories</h1>"
            "<form method='post' action='/memories'>"
            "<input name='statement' placeholder='Memory statement' maxlength='4000' required>"
            "<select name='memory_type'><option value='fact'>Fact</option>"
            "<option value='observation'>Observation</option>"
            "<option value='inference'>Inference</option>"
            "<option value='preference'>Preference</option></select>"
            "<button>Add memory</button></form>" + "".join(rows) + "</body></html>"
        )

    @app.post("/memories", response_class=HTMLResponse)
    def add_memory(statement: str = Form(...), memory_type: str = Form("fact")) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_memory(session, user, statement, memory_type=memory_type)
        return memories()

    @app.post("/memories/{memory_id}/update", response_class=HTMLResponse)
    def edit_memory(memory_id: str, statement: str = Form(...)) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            update_memory(session, user, memory_id, statement=statement)
        return memories()

    @app.post("/memories/{memory_id}/delete", response_class=HTMLResponse)
    def remove_memory(memory_id: str) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            delete_memory(session, user, memory_id)
        return memories()

    @app.post("/memories/{memory_id}/restore", response_class=HTMLResponse)
    def restore_memory(memory_id: str) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            update_memory(session, user, memory_id, status="confirmed")
        return memories()

    @app.post("/memories/{memory_id}/confirm", response_class=HTMLResponse)
    def approve_memory(memory_id: str) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            confirm_memory(session, user, memory_id)
        return memories()

    return app
