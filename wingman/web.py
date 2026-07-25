"""FastAPI application."""

# The dashboard CSS and JavaScript are kept inline so the local app has no build step.
# ruff: noqa: E501

import json
from datetime import UTC, datetime
from html import escape
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wingman import __version__
from wingman.config import Settings, get_settings
from wingman.database import make_engine, session_factory
from wingman.lifecycle import is_paused, set_paused
from wingman.models import AgentRun, Conversation, ConversationSummary, User
from wingman.services import (
    add_memory_note,
    confirm_memory,
    create_event,
    create_memory,
    create_place,
    create_reminder,
    create_saved_idea,
    delete_memory,
    delete_memory_note,
    list_events,
    list_memories,
    list_memory_notes,
    list_places,
    list_reminders,
    list_saved_ideas,
    update_memory,
    update_memory_note,
)
from wingman.system import backup_database, export_user_data, safe_update


def code_panel(label: str, content: str, max_height: int = 420) -> str:
    panel_id = f"code-{uuid4().hex}"
    return (
        "<section class='code-panel'>"
        f"<div class='code-toolbar'><strong>{escape(label)}</strong>"
        f"<button type='button' onclick=\"copyCode('{panel_id}', this)\">Copy</button></div>"
        f"<pre id='{panel_id}' class='code-block' style='max-height:{max_height}px'>"
        f"{escape(content)}</pre></section>"
    )


NAV_ITEMS = (
    ("dashboard", "/", "gauge-high", "Dashboard"),
    ("health", "/health", "heart-pulse", "Health"),
    ("memories", "/memories", "brain", "Memories"),
    ("conversations", "/conversations", "comments", "Conversations"),
    ("planning", "/planning", "calendar-days", "Planning"),
    ("api-calls", "/api-calls", "code", "API calls"),
    ("retrieval", "/retrieval", "magnifying-glass-chart", "Retrieval"),
    ("settings", "/settings", "sliders", "Settings"),
    ("system", "/system", "gear", "System"),
)


def navigation(active: str = "") -> str:
    links = "".join(
        f"<a class='nav-link{' active' if key == active else ''}' href='{href}' "
        f"aria-current='{'page' if key == active else 'false'}'>"
        f"<i class='fa-solid fa-{icon}' aria-hidden='true'></i><span>{label}</span></a>"
        for key, href, icon, label in NAV_ITEMS
    )
    return (
        "<aside class='sidebar'>"
        "<a class='brand' href='/'><span class='brand-mark'><i class='fa-solid fa-feather-pointed' "
        "aria-hidden='true'></i></span><span>Wingman</span></a>"
        "<p class='sidebar-caption'>Private relationship assistant</p>"
        f"<nav class='nav-list' aria-label='Main navigation'>{links}</nav>"
        "<div class='sidebar-footer'><span class='status-dot'></span>Local workspace</div>"
        "</aside>"
    )


def page_shell(title: str, body: str, active: str = "") -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)} | Wingman</title>"
        "<link rel='preconnect' href='https://cdnjs.cloudflare.com'>"
        "<link rel='stylesheet' href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css'>"
        "<style>"
        ":root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "color:#182230;background:#f5f7fb;line-height:1.5}*{box-sizing:border-box}body{margin:0}"
        "a{color:#3157c8;text-decoration:none}a:hover{text-decoration:underline}.app-shell{display:flex;min-height:100vh}"
        ".sidebar{width:238px;background:#101827;color:#dbe5f5;padding:1.35rem 1rem;display:flex;flex-direction:column;gap:.55rem}"
        ".brand{display:flex;align-items:center;gap:.65rem;color:#fff;font-size:1.2rem;font-weight:750;padding:.3rem .55rem}"
        ".brand:hover{text-decoration:none}.brand-mark{display:grid;place-items:center;width:2rem;height:2rem;border-radius:.7rem;"
        "background:#6d7efc;color:white}.sidebar-caption{font-size:.77rem;color:#8fa0bb;margin:.1rem .65rem 1rem}"
        ".nav-list{display:grid;gap:.3rem}.nav-link{display:flex;align-items:center;gap:.7rem;color:#aab8ce;"
        "padding:.65rem .7rem;border-radius:.65rem;font-size:.9rem}.nav-link i{width:1.1rem;text-align:center}"
        ".nav-link:hover,.nav-link.active{color:#fff;background:#24314a;text-decoration:none}.nav-link.active{box-shadow:inset 3px 0 #8b98ff}"
        ".sidebar-footer{margin-top:auto;color:#8191aa;font-size:.76rem;padding:.7rem}.status-dot{display:inline-block;width:.45rem;height:.45rem;"
        "border-radius:50%;background:#50d890;margin-right:.35rem;vertical-align:middle}.main{flex:1;min-width:0;padding:2.4rem clamp(1.2rem,4vw,4rem)}"
        ".page-header{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;margin-bottom:1.7rem}.eyebrow{color:#65738a;"
        "font-size:.76rem;font-weight:750;letter-spacing:.08em;text-transform:uppercase;margin:0 0 .3rem}.page-header h1{margin:0;font-size:2rem;"
        "letter-spacing:-.03em}.muted{color:#68778d}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin:1.2rem 0 1.7rem}"
        ".stat-card,.panel,.quick-card{background:#fff;border:1px solid #e3e8f1;border-radius:1rem;box-shadow:0 8px 24px rgba(28,45,80,.05)}"
        ".stat-card{padding:1.1rem 1.2rem}.stat-icon{color:#5968df;margin-bottom:.6rem}.stat-value{display:block;font-size:1.7rem;font-weight:760}.stat-label{color:#68778d;font-size:.82rem}"
        ".panel{padding:1.25rem;margin:1rem 0}.panel h2,.panel h3{margin-top:0}.panel-header{display:flex;justify-content:space-between;align-items:center;gap:1rem}"
        ".quick-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1rem}.quick-card{padding:1rem;color:inherit}.quick-card:hover{border-color:#aab5ff;text-decoration:none;transform:translateY(-1px)}"
        ".quick-card i{color:#5968df;font-size:1.05rem}.quick-card strong{display:block;margin:.55rem 0 .2rem}.quick-card small{color:#68778d}"
        ".badge{display:inline-flex;align-items:center;border-radius:999px;padding:.2rem .55rem;font-size:.72rem;font-weight:700;background:#edf1ff;color:#4658c8}"
        ".stack{display:grid;gap:.7rem}.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.form-row{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}"
        "input,select,textarea{font:inherit;border:1px solid #cbd4e2;border-radius:.55rem;padding:.55rem .65rem;background:#fff;max-width:100%}"
        "button,.button{font:inherit;border:0;border-radius:.55rem;padding:.55rem .75rem;background:#4f60d8;color:#fff;cursor:pointer;font-weight:650}"
        "button:hover,.button:hover{background:#3f4fc1;text-decoration:none}.button-secondary{background:#eef1f8;color:#34425b}.button-danger{background:#fff0f0;color:#b13d4b}"
        ".code-panel{border:1px solid #d8dfeb;border-radius:.75rem;margin:1rem 0;overflow:hidden;background:#0d1117}.code-toolbar{display:flex;justify-content:space-between;"
        "align-items:center;padding:.55rem .75rem;background:#192231;color:#e5edf9;font-size:.82rem}.code-toolbar button{padding:.3rem .6rem;background:#34425b;font-size:.75rem}"
        ".code-block{margin:0;overflow:auto;padding:1rem;color:#c9d1d9;white-space:pre-wrap;word-break:break-word}.json-key{color:#79c0ff}.json-string{color:#a5d6ff}.json-number{color:#d2a8ff}.json-boolean{color:#ff7b72}.json-null{color:#ffa657}"
        ".record-list{display:grid;gap:.8rem;padding:0;list-style:none}.record{background:#fff;border:1px solid #e3e8f1;border-radius:.8rem;padding:1rem}.record p:last-child{margin-bottom:0}"
        "@media(max-width:760px){.app-shell{display:block}.sidebar{width:auto;padding:.8rem}.sidebar-caption,.sidebar-footer{display:none}.brand{display:inline-flex}.nav-list{display:flex;overflow:auto}.nav-link{white-space:nowrap}.main{padding:1.5rem 1rem}.page-header{display:block}.grid-2{grid-template-columns:1fr}}"
        "</style><script>"
        "function copyCode(id,button){const value=document.getElementById(id).textContent; navigator.clipboard.writeText(value).then(()=>{const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1200);});}"
        "function escapeCode(text){return text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll(String.fromCharCode(34),'&quot;');}"
        "function highlightJson(pre){const raw=pre.textContent;let html='',last=0;const pattern=/(\"(?:\\\\.|[^\"\\\\])*\")(\\s*:)?|\\b(true|false)\\b|\\bnull\\b|-?\\b\\d+(?:\\.\\d+)?\\b/g;raw.replace(pattern,(match,string,colon,boolean,index)=>{html+=escapeCode(raw.slice(last,index));const cls=colon?'json-key':boolean?'json-boolean':match==='null'?'json-null':string?'json-string':'json-number';html+=`<span class=\"${cls}\">${escapeCode(match)}</span>`;last=index+match.length;});pre.innerHTML=html+escapeCode(raw.slice(last));}document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('.code-block').forEach(highlightJson));"
        "</script></head><body><div class='app-shell'>"
        + navigation(active)
        + f"<main class='main'>{body}</main></div></body></html>"
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
        body = (
            f"<header class='page-header'><div><p class='eyebrow'>System overview</p>"
            f"<h1>Health</h1><p class='muted'>A quick view of the local services Wingman uses.</p></div>"
            f"<span class='badge'><span class='status-dot'></span>Local only</span></header>"
            "<div class='summary-grid'>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-database'></i></div><span class='stat-value'>{escape(database)}</span><span class='stat-label'>Database</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-brands fa-telegram'></i></div><span class='stat-value'>{escape(telegram)}</span><span class='stat-label'>Telegram</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-wand-magic-sparkles'></i></div><span class='stat-value'>{escape(openai)}</span><span class='stat-label'>OpenAI</span></div>"
            "</div>"
        )
        return page_shell("Health", body, "health")

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
        body = (
            f"<header class='page-header'><div><p class='eyebrow'>Private workspace</p>"
            f"<h1>Good to see you, {escape(active_settings.user_name)}</h1>"
            "<p class='muted'>Keep the important details close and the conversation natural.</p></div>"
            f"<span class='badge'><span class='status-dot'></span>Wingman {__version__}</span></header>"
            "<section class='summary-grid'>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-brain'></i></div><span class='stat-value'>{memory_count}</span><span class='stat-label'>Saved memories</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-comments'></i></div><span class='stat-value'>{conversation_count}</span><span class='stat-label'>Conversations</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-code'></i></div><span class='stat-value'>{api_call_count}</span><span class='stat-label'>Recorded API calls</span></div>"
            "</section><section class='panel'><div class='panel-header'><div><p class='eyebrow'>Workspace tools</p>"
            "<h2>Explore Wingman</h2></div><span class='muted'>Everything stays on this machine</span></div>"
            "<div class='quick-grid'>"
            "<a class='quick-card' href='/memories'><i class='fa-solid fa-brain'></i><strong>Memories</strong><small>Review facts, notes, and evidence.</small></a>"
            "<a class='quick-card' href='/planning'><i class='fa-solid fa-calendar-days'></i><strong>Planning</strong><small>Keep places, ideas, events, and reminders together.</small></a>"
            "<a class='quick-card' href='/retrieval'><i class='fa-solid fa-magnifying-glass-chart'></i><strong>Retrieval</strong><small>See why saved context was selected.</small></a>"
            "<a class='quick-card' href='/api-calls'><i class='fa-solid fa-code'></i><strong>API calls</strong><small>Inspect complete requests and responses.</small></a>"
            "<a class='quick-card' href='/conversations'><i class='fa-solid fa-comments'></i><strong>Conversations</strong><small>Read recent messages and summaries.</small></a>"
            "<a class='quick-card' href='/health'><i class='fa-solid fa-heart-pulse'></i><strong>Health</strong><small>Check local service status.</small></a>"
            "</div></section>"
        )
        return page_shell("Dashboard", body, "dashboard")

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
                    "<article class='record'>"
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
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Memory space</p><h1>Memories</h1>"
            "<p class='muted'>Review what Wingman knows, where it came from, and what can be changed.</p></div></header>"
            "<section class='panel'><div class='panel-header'><h2>Add a memory</h2><i class='fa-solid fa-plus'></i></div>"
            "<form class='form-row' method='post' action='/memories'>"
            "<input name='statement' placeholder='Memory statement' maxlength='4000' required>"
            "<select name='memory_type'><option value='fact'>Fact</option><option value='observation'>Observation</option>"
            "<option value='inference'>Inference</option><option value='preference'>Preference</option></select>"
            "<button><i class='fa-solid fa-plus' aria-hidden='true'></i> Add memory</button></form></section>"
            "<section class='record-list'>" + "".join(rows) + "</section>"
        )
        return page_shell("Memories", body, "memories")

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
        rows = []
        for log in logs:
            query_json = json.dumps(json.loads(log.query_json), indent=2, ensure_ascii=False)
            candidate_json = json.dumps(
                json.loads(log.candidates_json), indent=2, ensure_ascii=False
            )
            rows.append(
                "<article class='record'>"
                f"<h2>Query</h2><p>{escape(log.query_text)}</p>"
                f"<h3>Query details</h3>{code_panel('JSON query', query_json, 260)}"
                f"<h3>Ranked candidates</h3>"
                f"{code_panel('JSON candidates', candidate_json)}</article>"
            )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Memory diagnostics</p><h1>Retrieval inspector</h1>"
            "<p class='muted'>Inspect query details, ranked candidates, and the evidence behind each result.</p></div></header>"
            "<section class='record-list'>" + "".join(rows) + "</section>"
        )
        return page_shell("Retrieval inspector", body, "retrieval")

    @app.get("/planning", response_class=HTMLResponse)
    def planning() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            places = list_places(session, user, include_deleted=True)
            ideas = list_saved_ideas(session, user)
            events = list_events(session, user)
            reminders = list_reminders(session, user)
        place_rows = "".join(
            f"<li><strong>{escape(place.name)}</strong> {escape(place.status)} "
            f"{escape(place.address)} {escape(place.description)}</li>"
            for place in places
        )
        idea_rows = "".join(
            f"<li><strong>{escape(idea.title)}</strong> {escape(idea.reason)}</li>"
            for idea in ideas
        )
        event_rows = "".join(
            f"<li><strong>{escape(event.title)}</strong> {escape(event.start_at.isoformat())} "
            f"{escape(event.status)}</li>"
            for event in events
        )
        reminder_rows = "".join(
            f"<li><strong>{escape(reminder.title)}</strong> "
            f"{escape(reminder.scheduled_at.isoformat())} {escape(reminder.status)}</li>"
            for reminder in reminders
        )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Relationship planning</p><h1>Planning</h1>"
            "<p class='muted'>Collect places, ideas, events, and reminders in one calm workspace.</p></div></header>"
            "<div class='grid-2'><section class='panel'>"
            + "<h2>Add place</h2><form method='post' action='/planning/places'>"
            + "<input name='name' placeholder='Name' required>"
            + "<input name='address' placeholder='Address'>"
            + "<input name='city' placeholder='City'>"
            + "<input name='description' placeholder='Description'>"
            + "<button>Save place</button></form><ul>"
            + place_rows
            + "</ul></section><section class='panel'><h2>Add saved idea</h2><form method='post' action='/planning/ideas'>"
            + "<input name='title' placeholder='Idea' required>"
            + "<input name='reason' placeholder='Why it fits'>"
            + "<button>Save idea</button></form><ul>"
            + idea_rows
            + "</ul></section></div><div class='grid-2'><section class='panel'><h2>Add event</h2><form method='post' action='/planning/events'>"
            + "<input name='title' placeholder='Event' required>"
            + "<input name='start_at' type='datetime-local' required>"
            + "<input name='description' placeholder='Description'>"
            + "<button>Save event</button></form><ul>"
            + event_rows
            + "</ul></section><section class='panel'><h2>Add reminder</h2><form method='post' action='/planning/reminders'>"
            + "<input name='title' placeholder='Reminder' required>"
            + "<input name='scheduled_at' type='datetime-local' required>"
            + "<button>Save reminder</button></form><ul>"
            + reminder_rows
            + "</ul></section></div>"
        )
        return page_shell("Planning", body, "planning")

    def parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)

    @app.post("/planning/places", response_class=HTMLResponse)
    def add_place(
        name: str = Form(...),
        address: str = Form(""),
        city: str = Form(""),
        description: str = Form(""),
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_place(session, user, name, address, city, description)
        return planning()

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page() -> str:
        def mask(value: str) -> str:
            return "configured" if value else "not configured"

        body = (
            "<header class='page-header'><div><p class='eyebrow'>Configuration</p><h1>Settings</h1>"
            "<p class='muted'>Runtime values are read from the environment. Secrets stay masked here.</p></div></header>"
            "<section class='panel stack'>"
            + f"<p>Telegram token {mask(active_settings.telegram_bot_token)}</p>"
            + f"<p>OpenAI key {mask(active_settings.openai_api_key)}</p>"
            + f"<p>Owner ID "
            f"{escape(str(active_settings.telegram_owner_id or 'not configured'))}</p>"
            + f"<p>Main model {escape(active_settings.openai_main_model)}</p>"
            + f"<p>Timezone {escape(active_settings.timezone)}</p>"
            + "<p>This dashboard is local-only. Secrets remain masked and are configured through the environment.</p></section>"
        )
        return page_shell("Settings", body, "settings")

    @app.get("/system", response_class=HTMLResponse)
    def system_page() -> str:
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Controls</p><h1>System</h1>"
            "<p class='muted'>Manage the bot lifecycle and local data safely.</p></div></header>"
            "<section class='panel stack'>"
            + f"<p>Telegram bot {'paused' if is_paused(active_settings) else 'running'}</p>"
            + "<form method='post' action='/system/bot/pause'><button>Pause bot</button></form>"
            + "<form method='post' action='/system/bot/resume'><button>Resume bot</button></form>"
            + "<a href='/system/export'>Download JSON export</a>"
            + "<form method='post' action='/system/backup'><button>Backup database</button></form>"
            + "<form method='post' action='/system/update'><button><i class='fa-solid fa-rotate'></i> Safe Git update</button></form></section>"
        )
        return page_shell("System", body, "system")

    @app.get("/system/export")
    def export_json() -> Response:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            payload = export_user_data(session, user)
        response = Response(
            json.dumps(payload, default=str, indent=2, ensure_ascii=False),
            media_type="application/json",
        )
        response.headers["Content-Disposition"] = "attachment; filename=wingman-export.json"
        return response

    @app.post("/system/backup", response_class=HTMLResponse)
    def create_backup() -> str:
        path = backup_database(active_settings)
        return page_shell(
            "System",
            f"<section class='panel'><p><i class='fa-solid fa-circle-check'></i> Backup created at {escape(str(path))}</p></section>",
            "system",
        )

    @app.post("/system/update", response_class=HTMLResponse)
    def update_system() -> str:
        try:
            branch = safe_update(active_settings)
            message = f"Update completed on branch {branch}"
        except Exception as exc:
            message = f"Update failed {exc}"
        return page_shell(
            "System", f"<section class='panel'><p>{escape(message)}</p></section>", "system"
        )

    @app.post("/system/bot/pause", response_class=HTMLResponse)
    def pause_bot() -> str:
        set_paused(active_settings, True)
        return system_page()

    @app.post("/system/bot/resume", response_class=HTMLResponse)
    def resume_bot() -> str:
        set_paused(active_settings, False)
        return system_page()

    @app.post("/planning/ideas", response_class=HTMLResponse)
    def add_idea(title: str = Form(...), reason: str = Form("")) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_saved_idea(session, user, title, reason)
        return planning()

    @app.post("/planning/events", response_class=HTMLResponse)
    def add_event(
        title: str = Form(...), start_at: str = Form(...), description: str = Form("")
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_event(session, user, title, parse_datetime(start_at), description=description)
        return planning()

    @app.post("/planning/reminders", response_class=HTMLResponse)
    def add_reminder(title: str = Form(...), scheduled_at: str = Form(...)) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_reminder(session, user, title, parse_datetime(scheduled_at))
        return planning()

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
            try:
                formatted_request = json.dumps(
                    json.loads(run.request_snapshot or "{}"),
                    indent=2,
                    ensure_ascii=False,
                )
            except json.JSONDecodeError:
                formatted_request = run.request_snapshot or ""
            try:
                formatted_response = json.dumps(
                    json.loads(run.response_snapshot or "{}"),
                    indent=2,
                    ensure_ascii=False,
                )
            except json.JSONDecodeError:
                formatted_response = run.response_snapshot or ""
            cards.append(
                "<article class='record'>"
                f"<h2>{escape(run.model_name)} {escape(run.status)}</h2>"
                f"<p>Latency {run.latency_ms} ms. Input tokens {run.input_tokens}. "
                f"Output tokens {run.output_tokens}.</p>"
                f"<h3>Full request</h3>{code_panel('JSON request', formatted_request)}"
                f"<h3>Full response</h3>{code_panel('JSON response', formatted_response)}"
                f"<p>Error {escape(run.error or '')}</p></article>"
            )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>OpenAI diagnostics</p><h1>Latest API calls</h1>"
            "<p class='muted'>Every request and response is available in a fixed-height, copyable JSON panel.</p></div></header>"
            "<section class='record-list'>" + "".join(cards) + "</section>"
        )
        return page_shell("Latest API calls", body, "api-calls")

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
                    "<article class='record'>"
                    f"<h2>Conversation {conversation.id}</h2>"
                    f"<h3>Summary</h3><pre>{escape(summary.summary_text if summary else '')}</pre>"
                    f"<h3>Recent messages</h3>{messages}</article>"
                )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Conversation history</p><h1>Conversations</h1>"
            "<p class='muted'>Review recent messages and summaries without leaving the local workspace.</p></div></header>"
            "<section class='record-list'>" + "".join(cards) + "</section>"
        )
        return page_shell("Conversations", body, "conversations")

    return app
