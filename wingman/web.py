"""FastAPI application."""

from html import escape

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wingman import __version__
from wingman.config import Settings, get_settings
from wingman.database import make_engine, session_factory
from wingman.models import AgentRun, Conversation, ConversationSummary, User
from wingman.services import (
    add_memory_note,
    confirm_memory,
    create_memory,
    delete_memory,
    delete_memory_note,
    list_memories,
    list_memory_notes,
    update_memory,
    update_memory_note,
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

    def navigation() -> str:
        return (
            "<nav><a href='/'>Dashboard</a> | <a href='/health'>Health</a> | "
            "<a href='/memories'>Memories</a> | <a href='/conversations'>Conversations</a> | "
            "<a href='/api-calls'>API calls</a> | <a href='/retrieval'>Retrieval</a></nav>"
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            memory_count = len(list_memories(session, user))
            conversation_count = session.query(Conversation).filter_by(user_id=user.id).count()
            api_call_count = (
                session.query(AgentRun)
                .join(Conversation, AgentRun.conversation_id == Conversation.id)
                .filter(Conversation.user_id == user.id)
                .count()
            )
        return (
            "<html><head><title>Wingman dashboard</title></head><body>"
            + navigation()
            + "<h1>Wingman dashboard</h1>"
            + f"<p>Memories {memory_count}</p><p>Conversations {conversation_count}</p>"
            + f"<p>Recorded API calls {api_call_count}</p>"
            + "<p>Use the links above to inspect each tool.</p></body></html>"
        )

    @app.get("/memories", response_class=HTMLResponse)
    def memories() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            records = list_memories(session, user, include_deleted=True)
            rows = []
            for memory in records:
                action = "restore" if memory.status == "deleted" else "delete"
                action_label = "Restore" if action == "restore" else "Delete"
                notes = "".join(
                    f"<div><small>{escape(note.note_type)}</small>"
                    f"<form method='post' action='/notes/{note.id}/update'>"
                    f"<input name='note_text' value='{escape(note.text, quote=True)}' "
                    "maxlength='2000' required><button>Save note</button></form>"
                    f"<form method='post' action='/notes/{note.id}/delete'>"
                    "<button>Remove note</button></form></div>"
                    for note in list_memory_notes(session, user, memory.id)
                )
                card = (
                    "<article style='border:1px solid #ddd;padding:1rem;margin:1rem 0'>"
                    f"<p><strong>{memory.type}</strong> {memory.status}</p>"
                    f"<p>{escape(memory.statement)}</p>"
                    f"{notes}<form method='post' action='/memories/{memory.id}/update'>"
                    f"<input name='statement' value='{escape(memory.statement, quote=True)}' "
                    "maxlength='4000' required><button>Save</button></form>"
                    f"<form method='post' action='/memories/{memory.id}/notes'>"
                    "<input name='note_text' placeholder='Evidence or context' "
                    "maxlength='2000' required>"
                    "<button>Add note</button></form>"
                    f"<form method='post' action='/memories/{memory.id}/{action}' "
                    "style='display:inline'>"
                    f"<button>{action_label}</button></form>"
                )
                if memory.status == "inferred":
                    card += (
                        f"<form method='post' action='/memories/{memory.id}/confirm' "
                        "style='display:inline'><button>Confirm</button></form>"
                    )
                card += "</article>"
                rows.append(card)
        return (
            "<html><head><title>Wingman memories</title></head><body>"
            + navigation()
            + "<h1>Memories</h1>"
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

    @app.post("/memories/{memory_id}/notes", response_class=HTMLResponse)
    def add_note(
        memory_id: str,
        note_text: str = Form(...),
        note_type: str = Form("evidence"),
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            add_memory_note(session, user, memory_id, note_text, note_type)
        return memories()

    @app.post("/notes/{note_id}/update", response_class=HTMLResponse)
    def edit_note(
        note_id: str,
        note_text: str = Form(...),
        note_type: str = Form("evidence"),
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            update_memory_note(session, user, note_id, note_text, note_type)
        return memories()

    @app.post("/notes/{note_id}/delete", response_class=HTMLResponse)
    def remove_note(note_id: str) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            delete_memory_note(session, user, note_id)
        return memories()

    @app.get("/retrieval", response_class=HTMLResponse)
    def retrieval_inspector() -> str:
        from wingman.models import RetrievalLog

        with session_factory(active_settings)() as session:
            user = web_user(session)
            logs = list(
                session.scalars(
                    select(RetrievalLog)
                    .where(RetrievalLog.user_id == user.id)
                    .order_by(RetrievalLog.created_at.desc())
                    .limit(20)
                )
            )
        rows = "".join(
            f"<li>{escape(log.query_text)} <pre>{escape(log.selected_json)}</pre></li>"
            for log in logs
        )
        return (
            f"<html><body>{navigation()}<h1>Retrieval inspector</h1><ul>{rows}</ul></body></html>"
        )

    @app.get("/api-calls", response_class=HTMLResponse)
    def api_calls() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            runs = list(
                session.scalars(
                    select(AgentRun)
                    .join(Conversation, AgentRun.conversation_id == Conversation.id)
                    .where(Conversation.user_id == user.id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(50)
                )
            )
        cards = []
        for run in runs:
            cards.append(
                "<article style='border:1px solid #ddd;padding:1rem;margin:1rem 0'>"
                f"<h2>{escape(run.model_name)} {escape(run.status)}</h2>"
                f"<p>Latency {run.latency_ms} ms. Input tokens {run.input_tokens}. "
                f"Output tokens {run.output_tokens}.</p>"
                f"<h3>Full request</h3><pre>{escape(run.request_snapshot or '')}</pre>"
                f"<h3>Full response</h3><pre>{escape(run.response_snapshot or '')}</pre>"
                f"<p>Error {escape(run.error or '')}</p></article>"
            )
        return (
            "<html><body>"
            + navigation()
            + "<h1>Latest API calls</h1>"
            + "".join(cards)
            + "</body></html>"
        )

    @app.get("/conversations", response_class=HTMLResponse)
    def conversations() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            records = list(
                session.scalars(
                    select(Conversation)
                    .where(Conversation.user_id == user.id)
                    .order_by(Conversation.created_at.desc())
                )
            )
            cards = []
            for conversation in records:
                summary = session.scalar(
                    select(ConversationSummary).where(
                        ConversationSummary.conversation_id == conversation.id
                    )
                )
                messages = "".join(
                    f"<p><strong>{escape(message.sender)}</strong> {escape(message.text)}</p>"
                    for message in conversation.messages[-20:]
                )
                cards.append(
                    "<article style='border:1px solid #ddd;padding:1rem;margin:1rem 0'>"
                    f"<h2>Conversation {conversation.id}</h2>"
                    f"<h3>Summary</h3><pre>{escape(summary.summary_text if summary else '')}</pre>"
                    f"<h3>Recent messages</h3>{messages}</article>"
                )
        return (
            "<html><body>"
            + navigation()
            + "<h1>Conversations</h1>"
            + "".join(cards)
            + "</body></html>"
        )

    return app
