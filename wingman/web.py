"""FastAPI application."""

# The dashboard CSS and JavaScript are kept inline so the local app has no build step.
# ruff: noqa: E501

import asyncio
import importlib.metadata
import json
import threading
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4
from zoneinfo import available_timezones

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wingman import __version__
from wingman.config import Settings, get_settings, save_runtime_settings
from wingman.database import make_engine, session_factory
from wingman.lifecycle import is_paused, schedule_restart, set_paused
from wingman.models import AgentRun, Conversation, ConversationSummary, Message, ToolExecution, User
from wingman.prompting import load_prompt, save_prompt
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
    message_display_text,
    purge_planning_record,
    update_memory,
    update_memory_note,
)
from wingman.system import (
    backup_database,
    database_diagnostics,
    export_user_data,
    import_user_data,
    read_update_status,
    repository_version,
    safe_update,
    write_update_status,
)
from wingman.telegram_bot import MESSAGE_BATCH_WINDOW_SECONDS, media_tool_path

HEALTH_DEPENDENCIES = (
    ("aiogram", "Telegram client"),
    ("openai", "OpenAI client"),
    ("fastapi", "Dashboard server"),
    ("sqlalchemy", "Database layer"),
    ("pydantic-settings", "Configuration"),
)


def dependency_status() -> list[dict[str, str]]:
    results = []
    for package, purpose in HEALTH_DEPENDENCIES:
        try:
            version = importlib.metadata.version(package)
            results.append(
                {"name": package, "purpose": purpose, "status": "pass", "detail": version}
            )
        except importlib.metadata.PackageNotFoundError:
            results.append(
                {"name": package, "purpose": purpose, "status": "fail", "detail": "Not installed"}
            )
    for tool in ("ffmpeg", "ffprobe"):
        results.append(
            {
                "name": tool,
                "purpose": "Video processing",
                "status": "pass" if media_tool_path(tool) else "fail",
                "detail": media_tool_path(tool) or "Not installed",
            }
        )
    return results


async def check_telegram_connection(settings: Settings) -> str:
    if not settings.telegram_bot_token:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot

    async with Bot(settings.telegram_bot_token) as bot:
        bot_info = await bot.get_me()
    return f"Connected as @{bot_info.username or bot_info.first_name}"


async def check_openai_connection(settings: Settings) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is not configured")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=10.0, max_retries=0)
    try:
        models = await client.models.list()
        return f"Connected, {len(models.data)} models visible"
    finally:
        await client.close()


def persistence_check(settings: Settings, check_name: str) -> str:
    with session_factory(settings)() as session:
        user = None
        if settings.telegram_owner_id is None:
            raise RuntimeError("Telegram owner ID is not configured")
        user = web_user_for_check(session, settings)
        marker = f"__wingman_health_check_{check_name}__"
        if check_name == "memory":
            memory_record = create_memory(session, user, marker)
            delete_memory(session, user, memory_record.id)
        else:
            place = create_place(session, user, marker)
            if check_name == "place":
                purge_planning_record(session, user, "place", place.id)
            elif check_name == "idea":
                idea_record = create_saved_idea(session, user, marker, "health check", place.id)
                purge_planning_record(session, user, "idea", idea_record.id)
                purge_planning_record(session, user, "place", place.id)
            elif check_name == "event":
                event_record = create_event(
                    session,
                    user,
                    marker,
                    datetime.now(UTC) + timedelta(minutes=5),
                    place_id=place.id,
                )
                purge_planning_record(session, user, "event", event_record.id)
                purge_planning_record(session, user, "place", place.id)
            elif check_name == "reminder":
                reminder_record = create_reminder(
                    session, user, marker, datetime.now(UTC) + timedelta(minutes=5)
                )
                purge_planning_record(session, user, "reminder", reminder_record.id)
                purge_planning_record(session, user, "place", place.id)
            else:
                raise RuntimeError("Unknown persistence check")
    return "Created, verified, and removed a temporary record"


def web_user_for_check(session: Session, settings: Settings) -> User:
    user = session.scalar(select(User).where(User.telegram_user_id == settings.telegram_owner_id))
    if user is None:
        user = User(telegram_user_id=settings.telegram_owner_id, name=settings.user_name)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def run_health_check(settings: Settings, name: str) -> dict[str, str]:
    goals = {
        "telegram": "Telegram getMe succeeds without sending a message",
        "openai": "OpenAI model listing succeeds without a completion",
        "video": "ffmpeg and ffprobe are available",
        "voice": "A transcription model is configured",
        "queue": "The message batching window is configured",
        "memory": "Memory persistence can create, verify, and clean up a record",
        "place": "Place persistence can create, verify, and clean up a record",
        "idea": "Saved idea persistence can create, verify, and clean up a record",
        "event": "Event persistence can create, verify, and clean up a record",
        "reminder": "Reminder persistence can create, verify, and clean up a record",
    }
    try:
        if name == "telegram":
            detail = asyncio.run(check_telegram_connection(settings))
        elif name == "openai":
            detail = asyncio.run(check_openai_connection(settings))
        elif name == "video":
            if not media_tool_path("ffmpeg") or not media_tool_path("ffprobe"):
                raise RuntimeError("ffmpeg or ffprobe is not installed")
            detail = "ffmpeg and ffprobe are available"
        elif name == "voice":
            if not settings.openai_transcription_model:
                raise RuntimeError("No transcription model is configured")
            detail = settings.openai_transcription_model
        elif name == "queue":
            if MESSAGE_BATCH_WINDOW_SECONDS <= 0:
                raise RuntimeError("Message batching is disabled")
            detail = f"{MESSAGE_BATCH_WINDOW_SECONDS:.1f} second debounce window"
        else:
            detail = persistence_check(settings, name)
        return {"name": name, "goal": goals[name], "status": "pass", "detail": detail}
    except Exception as exc:
        return {"name": name, "goal": goals[name], "status": "fail", "detail": str(exc)}


TIMEZONE_CITIES = {
    "Philadelphia, PA, USA": "America/New_York",
    "New York, NY, USA": "America/New_York",
    "Chicago, IL, USA": "America/Chicago",
    "Denver, CO, USA": "America/Denver",
    "Phoenix, AZ, USA": "America/Phoenix",
    "Los Angeles, CA, USA": "America/Los_Angeles",
    "Toronto, ON, Canada": "America/Toronto",
    "London, UK": "Europe/London",
    "Paris, France": "Europe/Paris",
    "Tokyo, Japan": "Asia/Tokyo",
    "Sydney, Australia": "Australia/Sydney",
}


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
    ("context", "/context", "layer-group", "Context"),
    ("conversations", "/conversations", "comments", "Conversations"),
    ("planning", "/planning", "calendar-days", "Planning"),
    ("api-calls", "/api-calls", "code", "API calls"),
    ("logs", "/logs", "list-check", "Logs"),
    ("usage", "/usage", "chart-column", "Usage"),
    ("retrieval", "/retrieval", "magnifying-glass-chart", "Retrieval"),
    ("settings", "/settings", "sliders", "Settings"),
    ("system", "/system", "gear", "System"),
)

PRICING_PER_MILLION = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4o-mini-transcribe": (1.25, 5.00),
    "text-embedding-3-small": (0.02, 0.00),
}


def usage_operation(run: AgentRun) -> str:
    try:
        request = json.loads(run.request_snapshot or "{}")
    except json.JSONDecodeError:
        request = {}
    if request.get("type") == "rolling_summary":
        return "summary"
    if request.get("type") == "audio_transcription":
        return "transcription"
    if request.get("video_diagnostics", {}).get("count", 0):
        return "video"
    if request.get("document_diagnostics", {}).get("count", 0):
        return "documents"
    if request.get("image_diagnostics", {}).get("count", 0):
        return "images"
    return "replies"


def usage_cost(run: AgentRun) -> float | None:
    rates = PRICING_PER_MILLION.get(run.model_name)
    if rates is None or run.input_tokens is None and run.output_tokens is None:
        return None
    return round(
        ((run.input_tokens or 0) * rates[0] + (run.output_tokens or 0) * rates[1]) / 1_000_000,
        8,
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
        "<link rel='icon' href='/assets/favicon/favicon.svg' type='image/svg+xml'>"
        "<link rel='alternate icon' href='/assets/favicon/favicon.ico'>"
        "<link rel='apple-touch-icon' href='/assets/favicon/apple-touch-icon.png'>"
        "<link rel='manifest' href='/assets/favicon/site.webmanifest'>"
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
        "border-radius:50%;background:#50d890;margin-right:.35rem;vertical-align:middle}.main{flex:1;min-width:0;width:100%;max-width:1180px;margin:0 auto;padding:2.4rem clamp(1.2rem,4vw,4rem);overflow:hidden}"
        ".page-header{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;margin-bottom:1.7rem}.eyebrow{color:#65738a;"
        "font-size:.76rem;font-weight:750;letter-spacing:.08em;text-transform:uppercase;margin:0 0 .3rem}.page-header h1{margin:0;font-size:2rem;"
        "letter-spacing:-.03em}.muted{color:#68778d}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin:1.2rem 0 1.7rem}"
        ".stat-card,.panel,.quick-card,.record{background:#fff;border:1px solid #e3e8f1;border-radius:1rem;box-shadow:0 8px 24px rgba(28,45,80,.05)}"
        ".stat-card{padding:1.1rem 1.2rem}.stat-icon{color:#5968df;margin-bottom:.6rem}.stat-value{display:block;font-size:1.7rem;font-weight:760}.stat-label{color:#68778d;font-size:.82rem}"
        ".panel{padding:1.35rem;margin:1rem 0}.panel h2,.panel h3{margin-top:0}.panel-header{display:flex;justify-content:space-between;align-items:center;gap:1rem}.panel-header h2{display:flex;align-items:center;gap:.55rem}.panel-header h2 i,.section-title i{color:#5968df;font-size:.95em}"
        ".quick-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1rem}.quick-card{padding:1rem;color:inherit}.quick-card:hover{border-color:#aab5ff;text-decoration:none;transform:translateY(-1px)}"
        ".quick-card i{color:#5968df;font-size:1.05rem}.quick-card strong{display:block;margin:.55rem 0 .2rem}.quick-card small{color:#68778d}"
        ".badge{display:inline-flex;align-items:center;border-radius:999px;padding:.2rem .55rem;font-size:.72rem;font-weight:700;background:#edf1ff;color:#4658c8}"
        ".stack{display:grid;gap:.8rem}.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.form-row{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.85rem}.field{display:grid;gap:.35rem}.field-wide{grid-column:1/-1}.field label,.stack>label{display:grid;gap:.35rem;font-size:.82rem;font-weight:700;color:#42516a}.form-actions{display:flex;flex-wrap:wrap;gap:.55rem;align-items:center}.compact-form{padding:.8rem;border-radius:.7rem;background:#f7f9fc;border:1px solid #e7ebf3}"
        "input,select,textarea{font:inherit;border:1px solid #cbd4e2;border-radius:.55rem;padding:.6rem .7rem;background:#fff;max-width:100%;width:100%;color:#182230}textarea{min-height:7rem;resize:vertical}input:focus,select:focus,textarea:focus{outline:3px solid rgba(89,104,223,.16);border-color:#7180e8}"
        "button,.button{font:inherit;border:0;border-radius:.55rem;padding:.55rem .75rem;background:#4f60d8;color:#fff;cursor:pointer;font-weight:650}"
        "button:hover,.button:hover{background:#3f4fc1;text-decoration:none}.button-secondary{background:#eef1f8;color:#34425b}.button-danger{background:#fff0f0;color:#b13d4b}"
        ".code-panel{border:1px solid #d8dfeb;border-radius:.75rem;margin:1rem 0;overflow:hidden;background:#0d1117}.code-toolbar{display:flex;justify-content:space-between;"
        "align-items:center;padding:.55rem .75rem;background:#192231;color:#e5edf9;font-size:.82rem}.code-toolbar button{padding:.3rem .6rem;background:#34425b;font-size:.75rem}"
        ".code-block{margin:0;overflow:auto;padding:1rem;color:#c9d1d9;white-space:pre-wrap;word-break:break-word}.json-key{color:#79c0ff}.json-string{color:#a5d6ff}.json-number{color:#d2a8ff}.json-boolean{color:#ff7b72}.json-null{color:#ffa657}"
        ".usage-day{display:grid;grid-template-columns:7rem 1fr 6rem;gap:.7rem;align-items:center;margin:.75rem 0;font-size:.82rem}.usage-bar{height:1rem;display:flex;overflow:hidden;border-radius:999px;background:#eef1f7}.usage-bar span{height:100%}table{width:100%;border-collapse:collapse;font-size:.83rem}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #edf0f5;white-space:nowrap}th{color:#53627b;background:#f7f9fc}"
        ".usage-axis{color:#68778d;font-size:.76rem;text-transform:uppercase;letter-spacing:.05em}.usage-chart{height:220px;display:flex;align-items:end;gap:.65rem;padding:1rem .5rem 0;border-bottom:1px solid #cbd4e2}.usage-column{height:100%;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:end;gap:.35rem;min-width:2.3rem}.usage-column-value{font-size:.68rem;color:#68778d;white-space:nowrap}.usage-column-bar{width:70%;min-height:0;border-radius:.45rem .45rem 0 0;background:linear-gradient(180deg,#7787f4,#5968df)}.usage-column small{color:#68778d;font-size:.7rem}.usage-chart-x{text-align:center;color:#68778d;font-size:.75rem;margin-top:.5rem}.active{box-shadow:inset 0 0 0 2px #5968df}"
        ".record-list{display:grid;gap:1rem;padding:0;list-style:none;min-width:0}.record{padding:1.15rem;min-width:0}.record p:last-child{margin-bottom:0}.record-top,.record-actions,.note-header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.6rem}.record-top{margin-bottom:.8rem}.record-actions{justify-content:flex-start;margin-top:1rem}.record-actions form{margin:0}.record-actions button,.form-actions button{display:inline-flex;align-items:center;gap:.4rem}.record-meta{display:flex;flex-wrap:wrap;gap:.4rem}.record-statement{font-size:1.08rem;line-height:1.55;margin:0 0 1rem}.note-list{display:grid;gap:.65rem;margin:1rem 0}.note-item{padding:.75rem;border-left:3px solid #aab5ff;background:#f7f9fc;border-radius:0 .6rem .6rem 0}.note-item small{color:#5968df;font-weight:750;text-transform:uppercase;letter-spacing:.04em}.note-item p{margin:.25rem 0 .55rem}.note-item form{display:flex;gap:.5rem;align-items:center}.note-item input{flex:1}.edit-form{border-top:1px solid #edf0f5;padding-top:1rem}.item-list{display:grid;gap:.55rem;padding:0;margin:1rem 0 0;list-style:none}.item-row{display:flex;align-items:flex-start;gap:.65rem;padding:.75rem;border:1px solid #edf0f5;border-radius:.65rem;background:#fbfcfe}.item-row i{color:#5968df;margin-top:.22rem}.item-row strong{display:block}.item-row small{display:block;color:#68778d;margin-top:.15rem}.planning-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.planning-grid .panel{margin:0}.conversation-list{display:grid;gap:.8rem;min-width:0}.message{max-width:82%;min-width:0;padding:.8rem 1rem;border-radius:1rem;box-shadow:0 3px 12px rgba(28,45,80,.05)}.message p,.conversation-summary{margin:.25rem 0 0;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}.conversation-summary{max-height:260px;overflow:auto;padding:.85rem;background:#f7f9fc;border-radius:.65rem;color:#42516a}.message-user{margin-left:auto;background:#e7ebff;border-bottom-right-radius:.25rem}.message-assistant{margin-right:auto;background:#fff;border:1px solid #e3e8f1;border-bottom-left-radius:.25rem}.message-label{display:flex;align-items:center;gap:.4rem;font-size:.75rem;font-weight:750;color:#5968df}.message-label i{font-size:.72rem}.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.settings-grid h2{grid-column:1/-1;margin-bottom:0}.settings-grid .field-wide{grid-column:1/-1}"
        ".health-check-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem;margin-top:1rem}.health-check{padding:.9rem;border:1px solid #edf0f5;border-radius:.7rem;background:#fbfcfe}.health-check strong{display:block}.health-check small{display:block;color:#68778d;margin-top:.2rem}.health-check p{min-height:2.4rem}.health-check .badge{background:#eef1f8;color:#68778d}.health-check .record-top{margin-bottom:.3rem}.health-check form{margin:0}@media(max-width:760px){.health-check-grid{grid-template-columns:1fr}}"
        "@media(max-width:760px){.app-shell{display:block}.sidebar{width:auto;padding:.8rem}.sidebar-caption,.sidebar-footer{display:none}.brand{display:inline-flex}.nav-list{display:flex;overflow:auto}.nav-link{white-space:nowrap}.main{padding:1.5rem 1rem}.page-header{display:block}.grid-2,.planning-grid,.form-grid,.settings-grid{grid-template-columns:1fr}.field-wide,.settings-grid h2{grid-column:auto}.message{max-width:94%}}"
        "</style><script>"
        "function copyCode(id,button){const value=document.getElementById(id).textContent; navigator.clipboard.writeText(value).then(()=>{const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1200);});}"
        "function escapeCode(text){return text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll(String.fromCharCode(34),'&quot;');}"
        "function highlightJson(pre){const raw=pre.textContent;let html='',last=0;const pattern=/(\"(?:\\\\.|[^\"\\\\])*\")(\\s*:)?|\\b(true|false)\\b|\\bnull\\b|-?\\b\\d+(?:\\.\\d+)?\\b/g;raw.replace(pattern,(match,string,colon,boolean,index)=>{html+=escapeCode(raw.slice(last,index));const cls=colon?'json-key':boolean?'json-boolean':match==='null'?'json-null':string?'json-string':'json-number';html+=`<span class=\"${cls}\">${escapeCode(match)}</span>`;last=index+match.length;});pre.innerHTML=html+escapeCode(raw.slice(last));}document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('.code-block').forEach(highlightJson));"
        "</script></head><body><div class='app-shell'>"
        + navigation(active)
        + f"<main class='main'>{body}</main></div></body></html>"
    )


def redact_diagnostic(value: object) -> object:
    """Redact common secret fields before diagnostic data reaches the browser."""
    secret_words = ("key", "token", "secret", "password", "authorization")
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if any(word in key.casefold() for word in secret_words)
            else redact_diagnostic(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_diagnostic(item) for item in value]
    return value


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="Wingman", version=__version__)
    health_results: dict[str, dict[str, str]] = {}

    @app.middleware("http")
    async def prevent_dashboard_caching(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith(
            (
                "/memories",
                "/planning",
                "/context",
                "/conversations",
                "/health",
                "/system",
                "/api-calls",
                "/logs",
                "/usage",
                "/retrieval",
                "/settings",
            )
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

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
        bot_state = "paused" if is_paused(active_settings) else "running"
        dependencies = dependency_status()
        dependency_rows = "".join(
            f"<div class='item-row'><i class='fa-solid fa-{'circle-check' if item['status'] == 'pass' else 'circle-xmark'}'></i><div><strong>{escape(item['name'])}</strong><small>{escape(item['purpose'])} · {escape(item['detail'])}</small></div></div>"
            for item in dependencies
        )
        check_names = (
            "telegram",
            "openai",
            "video",
            "voice",
            "queue",
            "memory",
            "place",
            "idea",
            "event",
            "reminder",
        )
        check_rows = "".join(
            "<article class='health-check'>"
            f"<div class='record-top'><div><strong>{escape(name.capitalize())}</strong><small>{escape(health_results.get(name, {}).get('goal', 'Not run yet'))}</small></div>"
            f"<span class='badge'>{escape(health_results.get(name, {}).get('status', 'not run'))}</span></div>"
            f"<p class='muted'>{escape(health_results.get(name, {}).get('detail', 'Run this check to verify the current system.'))}</p>"
            f"<form method='post' action='/health/check/{name}'><button class='button-secondary'>Test</button></form></article>"
            for name in check_names
        )
        body = (
            f"<header class='page-header'><div><p class='eyebrow'>System overview</p>"
            f"<h1>Health</h1><p class='muted'>A quick view of the local services Wingman uses.</p></div>"
            f"<span class='badge'><span class='status-dot'></span>Local only</span></header>"
            "<div class='summary-grid'>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-database'></i></div><span class='stat-value'>{escape(database)}</span><span class='stat-label'>Database</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-brands fa-telegram'></i></div><span class='stat-value'>{escape(telegram)}</span><span class='stat-label'>Telegram</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-wand-magic-sparkles'></i></div><span class='stat-value'>{escape(openai)}</span><span class='stat-label'>OpenAI</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-power-off'></i></div><span class='stat-value'>{escape(bot_state)}</span><span class='stat-label'>Bot state</span></div>"
            "</div>"
            "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-boxes-stacked'></i> Dependencies</h2><span class='muted'>Installed versions</span></div>"
            f"<div class='item-list'>{dependency_rows}</div></section>"
            "<section class='panel'><div class='panel-header'><div><h2 class='section-title'><i class='fa-solid fa-vial'></i> Functional checks</h2><p class='muted'>Checks use no model completions. Persistence checks create and remove temporary records.</p></div>"
            "<form method='post' action='/health/check-all'><button><i class='fa-solid fa-list-check'></i> Test all</button></form></div>"
            f"<div class='health-check-grid'>{check_rows}</div></section>"
        )
        return page_shell("Health", body, "health")

    @app.post("/health/check/{name}", response_class=HTMLResponse)
    def health_check(name: str) -> str:
        allowed = {
            "telegram",
            "openai",
            "video",
            "voice",
            "queue",
            "memory",
            "place",
            "idea",
            "event",
            "reminder",
        }
        if name not in allowed:
            raise HTTPException(status_code=404, detail="Unknown health check")
        health_results[name] = run_health_check(active_settings, name)
        return health()

    @app.post("/health/check-all", response_class=HTMLResponse)
    def health_check_all() -> str:
        for name in (
            "telegram",
            "openai",
            "video",
            "voice",
            "queue",
            "memory",
            "place",
            "idea",
            "event",
            "reminder",
        ):
            health_results[name] = run_health_check(active_settings, name)
        return health()

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
        elif active_settings.user_name and user.name != active_settings.user_name:
            user.name = active_settings.user_name
            session.commit()
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
            database_info = database_diagnostics(active_settings, session, user)
        read_at = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        revision = repository_version()
        body = (
            f"<header class='page-header'><div><p class='eyebrow'>Private workspace</p>"
            f"<h1>Good to see you, {escape(active_settings.user_name)}</h1>"
            "<p class='muted'>Keep the important details close and the conversation natural.</p></div>"
            f"<div class='stack'><span class='badge'><span class='status-dot'></span>Wingman {__version__} ({escape(revision['commit'][:12])})</span>"
            "<a class='button button-secondary' href='/?refresh=1'><i class='fa-solid fa-arrows-rotate'></i> Refresh</a></div></header>"
            "<section class='summary-grid'>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-brain'></i></div><span class='stat-value'>{memory_count}</span><span class='stat-label'>Saved memories</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-comments'></i></div><span class='stat-value'>{conversation_count}</span><span class='stat-label'>Conversations</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-code'></i></div><span class='stat-value'>{api_call_count}</span><span class='stat-label'>Recorded API calls</span></div>"
            "</section><section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-database'></i> Data source</h2>"
            f"<span class='muted'>Read at {escape(read_at)}</span></div>"
            f"<p class='muted'>This view uses the configured database and owner scope. It currently contains {database_info['memory_count']} memories and {database_info['place_count']} places.</p>"
            f"<p class='muted'>Database path {escape(str(database_info['database_path']))}</p></section>"
            "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-code-branch'></i> Loaded repository version</h2>"
            f"<span class='badge'>{escape(revision['branch'] or 'detached')}</span></div>"
            f"<p class='muted'><strong>Commit {escape(revision['commit'])}</strong></p>"
            f"<p>{escape(revision['message'])}</p></section>"
            "<section class='panel'><div class='panel-header'><div><p class='eyebrow'>Workspace tools</p>"
            "<h2>Explore Wingman</h2></div><span class='muted'>Everything stays on this machine</span></div>"
            "<div class='quick-grid'>"
            "<a class='quick-card' href='/memories'><i class='fa-solid fa-brain'></i><strong>Memories</strong><small>Review facts, notes, and evidence.</small></a>"
            "<a class='quick-card' href='/planning'><i class='fa-solid fa-calendar-days'></i><strong>Planning</strong><small>Keep places, ideas, events, and reminders together.</small></a>"
            "<a class='quick-card' href='/retrieval'><i class='fa-solid fa-magnifying-glass-chart'></i><strong>Retrieval</strong><small>See why saved context was selected.</small></a>"
            "<a class='quick-card' href='/api-calls'><i class='fa-solid fa-code'></i><strong>API calls</strong><small>Inspect complete requests and responses.</small></a>"
            "<a class='quick-card' href='/logs'><i class='fa-solid fa-list-check'></i><strong>Logs</strong><small>Trace tool calls, results, and persistence checks.</small></a>"
            "<a class='quick-card' href='/conversations'><i class='fa-solid fa-comments'></i><strong>Conversations</strong><small>Read recent messages and summaries.</small></a>"
            "<a class='quick-card' href='/health'><i class='fa-solid fa-heart-pulse'></i><strong>Health</strong><small>Check local service status.</small></a>"
            "</div></section>"
        )
        return page_shell("Dashboard", body, "dashboard")

    @app.get("/context", response_class=HTMLResponse)
    def context_page() -> str:
        prompt = escape(load_prompt(active_settings))
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Context design</p><h1>Context</h1>"
            "<p class='muted'>Control the editable conversation guidance and understand what changes each turn.</p></div></header>"
            "<section class='panel'><div class='panel-header'><div><h2 class='section-title'><i class='fa-solid fa-pen-to-square'></i> Static context</h2>"
            "<p class='muted'>This guidance is included on every model request. Application safety and tool rules remain protected in code.</p></div>"
            "<i class='fa-solid fa-file-pen'></i></div>"
            "<form method='post' action='/context'><textarea name='prompt' rows='18' maxlength='12000' style='width:100%' required>"
            f"{prompt}</textarea><p><button><i class='fa-solid fa-floppy-disk'></i> Save static context</button></p></form></section>"
            "<section class='panel'><div class='panel-header'><div><h2 class='section-title'><i class='fa-solid fa-layer-group'></i> Dynamic context</h2>"
            "<p class='muted'>This is assembled for each message based on the current conversation.</p></div>"
            "<i class='fa-solid fa-arrows-rotate'></i></div>"
            "<ul><li>Relevant saved memories and their notes</li>"
            "<li>Recent conversation messages</li><li>Conversation summaries when available</li>"
            "<li>Open memory proposals awaiting your answer</li>"
            "<li>Planning records when they are relevant to the conversation</li></ul>"
            "<p class='muted'>The system keeps this context within the configured token budget and does not send this dashboard explanation to the model.</p></section>"
        )
        return page_shell("Context", body, "context")

    @app.post("/context", response_class=HTMLResponse)
    def update_context(prompt: str = Form(...)) -> str:
        save_prompt(active_settings, prompt)
        return context_page()

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
                    "<div class='note-item'>"
                    f"<small>{escape(note.note_type)}</small><p>{escape(note.text)}</p>"
                    f"<form method='post' action='/notes/{note.id}/update'>"
                    f"<input name='note_text' value='{escape(note.text, quote=True)}' "
                    "maxlength='2000' required aria-label='Edit note'><button class='button-secondary'>"
                    "<i class='fa-solid fa-floppy-disk'></i> Save</button></form>"
                    f"<form method='post' action='/notes/{note.id}/delete' class='record-actions'>"
                    "<button class='button-danger'><i class='fa-solid fa-trash'></i> Remove</button></form></div>"
                    for note in list_memory_notes(session, user, memory.id)
                )
                card = (
                    "<article class='record memory-card'><div class='record-top'><div class='record-meta'>"
                    f"<span class='badge'><i class='fa-solid fa-tag'></i> {escape(memory.type)}</span>"
                    f"<span class='badge'>{escape(memory.status)}</span></div></div>"
                    f"<p class='record-statement'>{escape(memory.statement)}</p>"
                    f"<div class='note-list'>{notes or "<p class='muted'>No notes yet.</p>"}</div>"
                    f"<form class='stack compact-form edit-form' method='post' action='/memories/{memory.id}/update'>"
                    "<label>Edit statement <textarea name='statement' maxlength='4000' required>"
                    f"{escape(memory.statement)}</textarea></label><div class='form-actions'><button>"
                    "<i class='fa-solid fa-floppy-disk'></i> Save statement</button></div></form>"
                    f"<form class='form-row' method='post' action='/memories/{memory.id}/notes'>"
                    "<input name='note_text' placeholder='Add evidence or context' maxlength='2000' required>"
                    "<button class='button-secondary'><i class='fa-solid fa-note-sticky'></i> Add note</button></form>"
                    "<div class='record-actions'>"
                    f"<form method='post' action='/memories/{memory.id}/{action}'><button class='button-danger'>"
                    f"<i class='fa-solid fa-{'rotate-left' if action == 'restore' else 'trash'}'></i> {action_label}</button></form>"
                )
                if memory.status == "inferred":
                    card += (
                        f"<form method='post' action='/memories/{memory.id}/confirm' "
                        "class='record-actions'><button><i class='fa-solid fa-check'></i> Confirm</button></form>"
                    )
                card += "</div></article>"
                rows.append(card)
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Memory space</p><h1>Memories</h1>"
            "<p class='muted'>Review what Wingman knows, where it came from, and what can be changed.</p></div></header>"
            "<section class='panel'><div class='panel-header'><h2><i class='fa-solid fa-plus'></i> Add a memory</h2></div>"
            "<form class='stack' method='post' action='/memories'>"
            "<label class='field'>Statement <textarea name='statement' placeholder='Write the detail you want Wingman to remember' maxlength='4000' required></textarea></label>"
            "<div class='form-actions'><select name='memory_type'><option value='fact'>Fact</option><option value='observation'>Observation</option>"
            "<option value='inference'>Inference</option><option value='preference'>Preference</option></select>"
            "<button><i class='fa-solid fa-plus' aria-hidden='true'></i> Add memory</button></div></form></section>"
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
    def planning(request: Request) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            include_deleted = request.query_params.get("show_deleted") == "1"
            places = list_places(session, user, include_deleted=include_deleted)
            ideas = list_saved_ideas(session, user, include_deleted=include_deleted)
            events = list_events(session, user, include_deleted=include_deleted)
            reminders = list_reminders(session, user, include_deleted=include_deleted)
        place_rows = "".join(
            f"<li class='item-row'><i class='fa-solid fa-location-dot'></i><div><strong>{escape(place.name)}</strong>"
            f"<small>{escape(place.status)} · {escape(place.city or place.address or 'Location unknown')}</small>"
            f"<small>{escape(place.description)}</small></div></li>"
            for place in places
        )
        idea_rows = "".join(
            f"<li class='item-row'><i class='fa-solid fa-lightbulb'></i><div><strong>{escape(idea.title)}</strong>"
            f"<small>{escape(idea.reason or 'No reason added yet')}</small></div></li>"
            for idea in ideas
        )
        event_rows = "".join(
            f"<li class='item-row'><i class='fa-solid fa-calendar-day'></i><div><strong>{escape(event.title)}</strong>"
            f"<small>{escape(event.start_at.isoformat())} · {escape(event.status)}</small>"
            f"<small>{escape(event.description)}</small></div></li>"
            for event in events
        )
        reminder_rows = "".join(
            f"<li class='item-row'><i class='fa-solid fa-bell'></i><div><strong>{escape(reminder.title)}</strong>"
            f"<small>{escape(reminder.scheduled_at.isoformat())} · {escape(reminder.status)}</small></div></li>"
            for reminder in reminders
        )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Relationship planning</p><h1>Planning</h1>"
            "<p class='muted'>Collect places, ideas, events, and reminders in one calm workspace.</p></div>"
            f"<a class='button button-secondary' href='/planning{'?show_deleted=0' if include_deleted else '?show_deleted=1'}'>"
            f"{'Hide deleted' if include_deleted else 'Show deleted'}</a></header>"
            "<div class='planning-grid'><section class='panel'>"
            + "<h2 class='section-title'><i class='fa-solid fa-location-dot'></i> Add place</h2><form class='stack compact-form' method='post' action='/planning/places'>"
            + "<input name='name' placeholder='Name' required><input name='address' placeholder='Address'>"
            + "<input name='city' placeholder='City'><textarea name='description' placeholder='Description'></textarea>"
            + "<button><i class='fa-solid fa-plus'></i> Save place</button></form><ul class='item-list'>"
            + place_rows
            + "</ul></section><section class='panel'><h2 class='section-title'><i class='fa-solid fa-lightbulb'></i> Add saved idea</h2><form class='stack compact-form' method='post' action='/planning/ideas'>"
            + "<input name='title' placeholder='Idea' required><textarea name='reason' placeholder='Why it fits'></textarea>"
            + "<button><i class='fa-solid fa-plus'></i> Save idea</button></form><ul class='item-list'>"
            + idea_rows
            + "</ul></section><section class='panel'><h2 class='section-title'><i class='fa-solid fa-calendar-day'></i> Add event</h2><form class='stack compact-form' method='post' action='/planning/events'>"
            + "<input name='title' placeholder='Event' required><input name='start_at' type='datetime-local' required>"
            + "<textarea name='description' placeholder='Description'></textarea><button><i class='fa-solid fa-plus'></i> Save event</button></form><ul class='item-list'>"
            + event_rows
            + "</ul></section><section class='panel'><h2 class='section-title'><i class='fa-solid fa-bell'></i> Add reminder</h2><form class='stack compact-form' method='post' action='/planning/reminders'>"
            + "<input name='title' placeholder='Reminder' required><input name='scheduled_at' type='datetime-local' required>"
            + "<button><i class='fa-solid fa-plus'></i> Save reminder</button></form><ul class='item-list'>"
            + reminder_rows
            + "</ul></section></div>"
        )
        return page_shell("Planning", body, "planning")

    def parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)

    @app.post("/planning/places", response_class=HTMLResponse)
    def add_place(
        request: Request,
        name: str = Form(...),
        address: str = Form(""),
        city: str = Form(""),
        description: str = Form(""),
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_place(session, user, name, address, city, description)
        return planning(request)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page() -> str:
        def mask(value: str) -> str:
            return "configured" if value else "not configured"

        timezone_options = "".join(
            f"<option value='{escape(zone, quote=True)}'{' selected' if zone == active_settings.timezone else ''}>{escape(zone.replace('_', ' ').replace('/', ' / '))}</option>"
            for zone in sorted(available_timezones())
        )
        city_options = "".join(
            f"<option value='{escape(city, quote=True)}'></option>" for city in TIMEZONE_CITIES
        )
        city_map = json.dumps(TIMEZONE_CITIES)

        body = (
            "<header class='page-header'><div><p class='eyebrow'>Configuration</p><h1>Settings</h1>"
            "<p class='muted'>Runtime values are read from the environment. Secrets stay masked here.</p></div></header>"
            "<section class='panel'><h2 class='section-title'><i class='fa-solid fa-sliders'></i> Connection and identity</h2>"
            "<form method='post' action='/settings' class='stack'>"
            "<div class='settings-grid'>"
            f"<label class='field'>Telegram bot token <input type='password' name='telegram_bot_token' placeholder='{mask(active_settings.telegram_bot_token)}'></label>"
            f"<label class='field'>OpenAI API key <input type='password' name='openai_api_key' placeholder='{mask(active_settings.openai_api_key)}'></label>"
            f"<label class='field'>Telegram owner ID <input name='telegram_owner_id' value='{escape(str(active_settings.telegram_owner_id or ''))}'></label>"
            f"<label class='field'>Your name <input name='user_name' value='{escape(active_settings.user_name, quote=True)}'></label>"
            f"<label class='field'>Primary person's name <input name='primary_person_name' value='{escape(active_settings.primary_person_name, quote=True)}'></label>"
            "<h2 class='section-title'><i class='fa-solid fa-microchip'></i> Models</h2>"
            f"<label class='field'>Main model <input name='openai_main_model' value='{escape(active_settings.openai_main_model, quote=True)}'></label>"
            f"<label class='field'>Summary model <input name='openai_summary_model' value='{escape(active_settings.openai_summary_model, quote=True)}'></label>"
            "<h2 class='section-title'><i class='fa-solid fa-location-dot'></i> Local settings</h2>"
            f"<label class='field'>City or location <input id='timezone-city' list='timezone-cities' autocomplete='off' placeholder='Start typing a city, for example Philadelphia'><datalist id='timezone-cities'>{city_options}</datalist></label>"
            f"<label class='field'>Timezone <select id='timezone-select' name='timezone'>{timezone_options}</select></label></div>"
            f"<script>const timezoneCities={city_map};const cityInput=document.querySelector('#timezone-city');const cityList=document.querySelector('#timezone-cities');const timezoneSelect=document.querySelector('#timezone-select');let cityTimer;cityInput.addEventListener('input',()=>{{clearTimeout(cityTimer);const query=cityInput.value.trim();if(query.length<2)return;cityTimer=setTimeout(()=>fetch('https://geocoding-api.open-meteo.com/v1/search?name='+encodeURIComponent(query)+'&count=8&language=en&format=json').then(response=>response.json()).then(data=>{{cityList.replaceChildren();(data.results||[]).forEach(city=>{{const label=[city.name,city.admin1,city.country].filter(Boolean).join(', ');const option=document.createElement('option');option.value=label;option.dataset.timezone=city.timezone||'';cityList.appendChild(option);}});}}).catch(()=>{{}}),250);}});cityInput.addEventListener('change',()=>{{const option=[...cityList.options].find(item=>item.value===cityInput.value);const zone=option?.dataset.timezone||timezoneCities[cityInput.value];if(zone)timezoneSelect.value=zone;}});</script>"
            "<p><button><i class='fa-solid fa-floppy-disk'></i> Save settings</button></p></form></section>"
            "<section class='panel'><p>This dashboard is local-only. Blank secret fields keep the current values. Settings are stored in the local .env file, which is plaintext and should not be exposed.</p></section>"
        )
        return page_shell("Settings", body, "settings")

    @app.post("/settings", response_class=HTMLResponse)
    def update_settings(
        telegram_bot_token: str = Form(""),
        telegram_owner_id: str = Form(""),
        openai_api_key: str = Form(""),
        openai_main_model: str = Form(""),
        openai_summary_model: str = Form(""),
        user_name: str = Form(""),
        primary_person_name: str = Form(""),
        timezone: str = Form(""),
    ) -> str:
        try:
            save_runtime_settings(
                active_settings,
                {
                    "telegram_bot_token": telegram_bot_token,
                    "telegram_owner_id": telegram_owner_id,
                    "openai_api_key": openai_api_key,
                    "openai_main_model": openai_main_model,
                    "openai_summary_model": openai_summary_model,
                    "user_name": user_name,
                    "primary_person_name": primary_person_name,
                    "timezone": timezone,
                },
            )
        except (ValueError, OSError) as exc:
            return page_shell(
                "Settings",
                f"<section class='panel'><p>{escape(str(exc))}</p></section>",
                "settings",
            )
        return settings_page()

    @app.get("/system", response_class=HTMLResponse)
    def system_page() -> str:
        paused = is_paused(active_settings)
        revision = repository_version()
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Controls</p><h1>System</h1>"
            "<p class='muted'>Manage the bot lifecycle and local data safely.</p></div></header>"
            "<section class='panel stack'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-sliders'></i> Bot and data controls</h2></div>"
            + f"<p><span class='badge'><span class='status-dot'></span>Telegram bot {'paused' if paused else 'running'}</span></p>"
            + f"<form method='post' action='/system/bot/{'resume' if paused else 'pause'}'><button>"
            + f"<i class='fa-solid fa-{'play' if paused else 'pause'}'></i> {'Resume bot' if paused else 'Pause bot'}</button></form>"
            + "<p><a class='button button-secondary' href='/system/export'><i class='fa-solid fa-download'></i> Download JSON export</a></p>"
            + "<form method='post' action='/system/import' enctype='multipart/form-data'><label>Import JSON export <input type='file' name='export_file' accept='.json,application/json' required></label> <button class='button-secondary'><i class='fa-solid fa-upload'></i> Import data</button></form>"
            + "<form method='post' action='/system/backup'><button>Backup database</button></form>"
            + "</section>"
            + "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-code-branch'></i> Repository update</h2>"
            + f"<span class='badge'>{escape(revision['branch'] or 'detached')}</span></div>"
            + f"<p><strong>Version {escape(__version__)}</strong></p><p><strong>Commit {escape(revision['commit'])}</strong></p>"
            + f"<p>{escape(revision['message'])}</p>"
            + "<form method='post' action='/system/update'><button><i class='fa-solid fa-rotate'></i> Safe Git update</button></form></section>"
        )
        return page_shell("System", body, "system")

    @app.get("/system/update-progress", response_class=HTMLResponse)
    def update_progress_page() -> str:
        update = read_update_status(active_settings)
        status = str(update.get("status", "idle"))
        logs = "\n".join(str(item) for item in update.get("logs", []))
        message = (
            "Update completed. You can return to the dashboard."
            if status == "completed"
            else "The update is running. This page will refresh its log automatically."
        )
        if status == "failed":
            message = f"Update failed. {update.get('error', '')}"
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Repository update</p><h1>Updating Wingman</h1>"
            f"<p class='muted'>{escape(message)}</p></div><span id='update-status' class='badge'>{escape(status)}</span></header>"
            "<section class='panel'><h2 class='section-title'><i class='fa-solid fa-terminal'></i> Update log</h2>"
            f"{code_panel('Live update output', logs or 'Waiting for the update to start.', 360)}"
            "<p id='update-return' class='form-actions'>"
            + (
                "<a class='button' href='/'>Return to dashboard</a>"
                if status in {"completed", "failed"}
                else ""
            )
            + "</p></section>"
            "<script>const updateTimer=setInterval(()=>fetch('/system/update-status').then(r=>r.json()).then(s=>{document.querySelector('#update-status').textContent=s.status;const pre=document.querySelector('.code-block');if(s.logs)pre.textContent=s.logs.join('\\n');if(s.status==='completed'||s.status==='failed'){clearInterval(updateTimer);document.querySelector('#update-return').innerHTML='<a class=\"button\" href=\"/\">Return to dashboard</a>';}}),1500);</script>"
        )
        return page_shell("Updating Wingman", body, "system")

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

    @app.post("/system/import", response_class=HTMLResponse)
    def import_json(export_file: Annotated[UploadFile, File(...)]) -> str:
        try:
            payload = json.loads(export_file.file.read().decode("utf-8"))
            with session_factory(active_settings)() as session:
                user = web_user(session)
                import_user_data(session, user, payload)
            message = "Import completed"
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            message = f"Import failed {exc}"
        return page_shell(
            "System", f"<section class='panel'><p>{escape(message)}</p></section>", "system"
        )

    @app.post("/system/update", response_class=HTMLResponse)
    def update_system() -> str:
        current = read_update_status(active_settings)
        if current.get("status") == "running":
            return update_progress_page()
        write_update_status(active_settings, "running", ["Update queued"])

        def run_update() -> None:
            try:
                safe_update(active_settings)
                schedule_restart()
            except Exception as exc:
                status = read_update_status(active_settings)
                write_update_status(
                    active_settings,
                    "failed",
                    [str(item) for item in status.get("logs", [])],
                    str(exc),
                    str(status.get("branch", "")),
                )

        threading.Thread(target=run_update, daemon=True).start()
        return update_progress_page()

    @app.get("/system/update-status")
    def update_status() -> dict[str, Any]:
        status = read_update_status(active_settings)
        return {
            "status": status.get("status", "idle"),
            "logs": status.get("logs", []),
            "error": status.get("error", ""),
            "branch": status.get("branch", ""),
        }

    @app.post("/system/bot/pause", response_class=HTMLResponse)
    def pause_bot() -> str:
        set_paused(active_settings, True)
        return system_page()

    @app.post("/system/bot/resume", response_class=HTMLResponse)
    def resume_bot() -> str:
        set_paused(active_settings, False)
        return system_page()

    @app.post("/planning/ideas", response_class=HTMLResponse)
    def add_idea(request: Request, title: str = Form(...), reason: str = Form("")) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_saved_idea(session, user, title, reason)
        return planning(request)

    @app.post("/planning/events", response_class=HTMLResponse)
    def add_event(
        request: Request,
        title: str = Form(...),
        start_at: str = Form(...),
        description: str = Form(""),
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_event(session, user, title, parse_datetime(start_at), description=description)
        return planning(request)

    @app.post("/planning/reminders", response_class=HTMLResponse)
    def add_reminder(
        request: Request, title: str = Form(...), scheduled_at: str = Form(...)
    ) -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            create_reminder(session, user, title, parse_datetime(scheduled_at))
        return planning(request)

    @app.get("/logs", response_class=HTMLResponse)
    def logs() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            executions = list(
                session.scalars(
                    select(ToolExecution)
                    .where(ToolExecution.user_id == user.id)
                    .order_by(ToolExecution.created_at.desc())
                    .limit(100)
                )
            )
            runs = list(
                session.scalars(
                    select(AgentRun)
                    .join(Conversation, AgentRun.conversation_id == Conversation.id)
                    .where(Conversation.user_id == user.id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(30)
                )
            )
        execution_cards = []
        for execution in executions:
            try:
                input_data = redact_diagnostic(json.loads(execution.input_json))
                input_text = json.dumps(input_data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                input_text = execution.input_json
            try:
                output_data = redact_diagnostic(json.loads(execution.output_json or "{}"))
                output_text = json.dumps(output_data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                output_text = execution.output_json or ""
            execution_cards.append(
                "<article class='record'>"
                f"<div class='record-top'><h2>{escape(execution.tool_name)}</h2>"
                f"<span class='badge'>{escape(execution.status)}</span></div>"
                f"<p class='muted'>{escape(execution.created_at.isoformat())}. Agent run {escape(execution.agent_run_id or 'none')}</p>"
                f"<h3>Tool input</h3>{code_panel('JSON input', input_text, 260)}"
                f"<h3>Tool output</h3>{code_panel('JSON output', output_text, 260)}"
                f"<p class='muted'>Error {escape(execution.error or 'none')}</p></article>"
            )
        run_cards = []
        for run in runs:
            response_data = run.response_snapshot or ""
            try:
                response_data = json.dumps(
                    redact_diagnostic(json.loads(response_data)),
                    indent=2,
                    ensure_ascii=False,
                )
            except json.JSONDecodeError:
                pass
            run_cards.append(
                "<article class='record'>"
                f"<div class='record-top'><h2>{escape(run.model_name)}</h2>"
                f"<span class='badge'>{escape(run.status)}</span></div>"
                f"<p class='muted'>{escape(run.created_at.isoformat())}. Error {escape(run.error or 'none')}</p>"
                f"{code_panel('Agent response summary', response_data, 300)}</article>"
            )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Runtime diagnostics</p><h1>Logs</h1>"
            "<p class='muted'>Inspect what tools were called, what they returned, and whether persistence was verified. Secrets are redacted.</p></div></header>"
            "<section class='panel'><h2 class='section-title'><i class='fa-solid fa-list-check'></i> Tool executions</h2>"
            + ("".join(execution_cards) or "<p class='muted'>No tool executions recorded yet.</p>")
            + "</section><section class='panel'><h2 class='section-title'><i class='fa-solid fa-robot'></i> Agent runs</h2>"
            + ("".join(run_cards) or "<p class='muted'>No agent runs recorded yet.</p>")
            + "</section>"
        )
        return page_shell("Logs", body, "logs")

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

    @app.get("/usage", response_class=HTMLResponse)
    def usage() -> str:
        with session_factory(active_settings)() as session:
            user = web_user(session)
            runs = list(
                session.scalars(
                    select(AgentRun)
                    .join(Conversation, AgentRun.conversation_id == Conversation.id)
                    .where(Conversation.user_id == user.id)
                    .order_by(AgentRun.created_at.asc())
                )
            )
        records: list[dict[str, Any]] = []
        today = datetime.now(UTC).date()
        days = [(today - timedelta(days=index)).isoformat() for index in range(9, -1, -1)]
        daily: dict[str, dict[str, dict[str, float]]] = {day: {} for day in days}
        for run in runs:
            operation = usage_operation(run)
            cost = usage_cost(run)
            day = run.created_at.date().isoformat()
            tokens = (run.input_tokens or 0) + (run.output_tokens or 0)
            if day in daily:
                daily[day].setdefault(operation, {"tokens": 0.0, "cost": 0.0})
                daily[day][operation]["tokens"] += tokens
                daily[day][operation]["cost"] += cost or 0.0
            records.append(
                {
                    "day": day,
                    "date": run.created_at.strftime("%Y-%m-%d %H:%M"),
                    "operation": operation,
                    "model": run.model_name,
                    "input": run.input_tokens,
                    "output": run.output_tokens,
                    "cost": cost,
                    "status": run.status,
                }
            )
        recent_records = [item for item in records if item["day"] in days]
        total_cost = sum(item["cost"] or 0 for item in recent_records)
        total_input = sum(item["input"] or 0 for item in recent_records)
        total_output = sum(item["output"] or 0 for item in recent_records)
        colors = {
            "replies": "#5968df",
            "summary": "#7c5ce5",
            "transcription": "#20a67a",
            "images": "#e49a3a",
            "documents": "#d65c86",
            "video": "#4b9ac7",
        }
        rows = []
        for item in reversed(records[-200:]):
            cost_text = f"${item['cost']:.8f}" if item["cost"] is not None else "Not estimated"
            rows.append(
                f"<tr data-day='{escape(item['day'])}' data-date='{escape(item['date'])}' data-operation='{escape(item['operation'])}' data-cost='{item['cost'] or 0}'>"
                f"<td>{escape(item['date'])}</td><td>{escape(item['operation'])}</td>"
                f"<td>{escape(item['model'])}</td><td>{item['input'] if item['input'] is not None else 'unknown'}</td>"
                f"<td>{item['output'] if item['output'] is not None else 'unknown'}</td><td>{cost_text}</td>"
                f"<td>{escape(item['status'])}</td></tr>"
            )
        chart_data = json.dumps(daily, ensure_ascii=False).replace("</", "<\\/")
        chart_script = (
            "<script>"
            f"const usageDays={chart_data};"
            "const usageColors=" + json.dumps(colors) + ";"
            "function renderUsage(mode){const keys=Object.keys(usageDays);const totals=keys.map(day=>Object.values(usageDays[day]).reduce((sum,item)=>sum+item[mode],0));const max=Math.max(...totals,1);const chart=document.querySelector('#usage-chart');chart.innerHTML=keys.map((day,index)=>`<div class=\"usage-column\" title=\"${day}: ${mode==='tokens'?totals[index].toLocaleString()+' tokens':'$'+totals[index].toFixed(8)}\"><span class=\"usage-column-value\">${mode==='tokens'?totals[index].toLocaleString():'$'+totals[index].toFixed(6)}</span><div class=\"usage-column-bar\" style=\"height:${Math.max(totals[index]/max*100,totals[index]?3:0)}%\"></div><small>${day.slice(5)}</small></div>`).join('');document.querySelector('#usage-axis').textContent=mode==='tokens'?'tokens':'dollars';const stack=document.querySelector('#usage-stack');stack.innerHTML=keys.map(day=>{const values=usageDays[day];const total=Object.values(values).reduce((sum,item)=>sum+item[mode],0);const segments=Object.entries(values).map(([operation,item])=>`<span title=\"${operation}\" style=\"width:${total?item[mode]/total*100:0}%;background:${usageColors[operation]||'#8792a8'}\"></span>`).join('');return `<div class=\"usage-day\"><span>${day}</span><div class=\"usage-bar\">${segments||'<span style=\"width:100%;background:#d8deea\"></span>'}</div><span>${mode==='tokens'?total.toLocaleString():'$'+total.toFixed(6)}</span></div>`}).join('');}"
            "renderUsage('tokens');document.querySelectorAll('[data-usage-mode]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-usage-mode]').forEach(item=>item.classList.remove('active'));button.classList.add('active');renderUsage(button.dataset.usageMode);}));"
            "const table=document.querySelector('#usage-table');const filter=document.querySelector('#usage-date-filter');const sort=document.querySelector('#usage-sort');function updateTable(){const rows=[...table.tBodies[0].rows].filter(row=>row.dataset.date);const query=filter.value;rows.forEach(row=>row.hidden=query&&!row.dataset.date.startsWith(query));const visible=rows.filter(row=>!row.hidden);visible.sort((a,b)=>{const key=sort.value;const left=key==='cost'?Number(a.dataset.cost):key==='operation'?a.dataset.operation:a.dataset.date;const right=key==='cost'?Number(b.dataset.cost):key==='operation'?b.dataset.operation:b.dataset.date;return sort.dataset.direction==='asc'?String(left).localeCompare(String(right),undefined,{numeric:true}):String(right).localeCompare(String(left),undefined,{numeric:true});});visible.forEach(row=>table.tBodies[0].appendChild(row));}filter.addEventListener('input',updateTable);sort.addEventListener('change',updateTable);document.querySelector('#usage-sort-direction').addEventListener('click',event=>{sort.dataset.direction=sort.dataset.direction==='asc'?'desc':'asc';event.target.textContent=sort.dataset.direction==='asc'?'Ascending':'Descending';updateTable();});"
            "</script>"
        )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Usage accounting</p><h1>Cost and usage</h1>"
            "<p class='muted'>The charts show the last ten days. Reported token usage is used when the provider returns it.</p></div></header>"
            "<div class='summary-grid'>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-dollar-sign'></i></div><span class='stat-value'>${total_cost:.6f}</span><span class='stat-label'>Estimated cost</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-arrow-down'></i></div><span class='stat-value'>{total_input:,}</span><span class='stat-label'>Input tokens</span></div>"
            f"<div class='stat-card'><div class='stat-icon'><i class='fa-solid fa-arrow-up'></i></div><span class='stat-value'>{total_output:,}</span><span class='stat-label'>Output tokens</span></div></div>"
            "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-chart-column'></i> Daily usage</h2>"
            "<div class='form-actions'><button class='button-secondary active' data-usage-mode='tokens'>Tokens</button><button class='button-secondary' data-usage-mode='cost'>Dollars</button></div></div>"
            "<div class='usage-axis'><span id='usage-axis'>tokens</span></div><div id='usage-chart' class='usage-chart'></div><div class='usage-chart-x'>Last ten days</div></section>"
            "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-layer-group'></i> Usage by operation</h2><span class='muted'>Same ten-day period</span></div>"
            "<div id='usage-stack'></div><p class='muted'>Colors separate replies, summaries, transcription, images, documents, and video.</p></section>"
            "<section class='panel'><div class='panel-header'><h2 class='section-title'><i class='fa-solid fa-table-list'></i> Operation details</h2><div class='form-actions'><label class='muted'>Date <input id='usage-date-filter' type='date'></label><label class='muted'>Sort <select id='usage-sort' data-direction='desc'><option value='date'>Date</option><option value='operation'>Operation</option><option value='cost'>Cost</option></select></label><button id='usage-sort-direction' class='button-secondary'>Descending</button></div></div>"
            "<div style='overflow:auto'><table id='usage-table'><thead><tr><th>Date</th><th>Operation</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th><th>Status</th></tr></thead><tbody>"
            + ("".join(rows) or "<tr><td colspan='7'>No usage recorded yet.</td></tr>")
            + "</tbody></table></div></section>"
            + chart_script
        )
        return page_shell("Cost and usage", body, "usage")

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
                recent_messages = list(
                    session.scalars(
                        select(Message)
                        .where(Message.conversation_id == conversation.id)
                        .order_by(Message.created_at.desc())
                        .limit(20)
                    )
                )
                messages = "".join(
                    f"<div class='message message-{'user' if message.sender == 'user' else 'assistant'}'>"
                    f"<div class='message-label'><i class='fa-solid fa-{'user' if message.sender == 'user' else 'robot'}'></i>"
                    f"{escape(message.sender.capitalize())}</div><p>{escape(message_display_text(session, message))}</p></div>"
                    for message in reversed(recent_messages)
                )
                cards.append(
                    "<article class='record'>"
                    f"<h2>Conversation {conversation.id}</h2>"
                    f"<h3 class='section-title'><i class='fa-solid fa-scroll'></i> Summary</h3><div class='conversation-summary'>{escape(summary.summary_text if summary else 'No rolling summary yet.')}</div>"
                    f"<h3 class='section-title'><i class='fa-solid fa-comments'></i> Recent messages</h3><div class='conversation-list'>{messages}</div></article>"
                )
        body = (
            "<header class='page-header'><div><p class='eyebrow'>Conversation history</p><h1>Conversations</h1>"
            "<p class='muted'>Review recent messages and summaries without leaving the local workspace.</p></div></header>"
            "<section class='record-list'>" + "".join(cards) + "</section>"
        )
        return page_shell("Conversations", body, "conversations")

    return app
