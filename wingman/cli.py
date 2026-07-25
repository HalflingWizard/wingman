"""Command line entry point."""

import argparse
import asyncio
import os
import signal
import threading
import webbrowser
from pathlib import Path

import uvicorn

from wingman import __version__
from wingman.config import Settings, get_settings
from wingman.database import initialize_database
from wingman.reminder_worker import run_reminder_worker
from wingman.system import safe_update
from wingman.telegram_bot import run_bot
from wingman.web import create_app

PID_FILE = Path(".wingman.pid")


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(prog="wingman")
    subparsers = command_parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--no-browser", action="store_true")
    start.add_argument("--daemon", action="store_true")
    for name in ("stop", "restart", "status", "update", "doctor"):
        subparsers.add_parser(name)
    return command_parser


def start(no_browser: bool) -> None:
    settings = get_settings()
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    initialize_database(settings)
    app = create_app()

    def web_server() -> None:
        uvicorn.run(app, host=settings.web_host, port=settings.web_port, log_level="info")

    thread = threading.Thread(target=web_server, daemon=True)
    thread.start()
    address = f"http://{settings.web_host}:{settings.web_port}/"
    print(f"Wingman {__version__} is running at {address}")
    if not no_browser:
        webbrowser.open(address)
    if settings.telegram_bot_token and settings.telegram_owner_id is not None:
        asyncio.run(run_services(settings))
    else:
        print("Telegram is not configured. The health page remains available.")
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass
    PID_FILE.unlink(missing_ok=True)


async def run_services(settings: Settings) -> None:
    await asyncio.gather(run_bot(settings), run_reminder_worker(settings))


def main() -> None:
    args = parser().parse_args()
    if args.command == "start":
        start(args.no_browser)
    elif args.command == "doctor":
        settings = get_settings()
        print(f"database {'configured' if settings.database_url else 'missing'}")
        telegram_status = (
            "configured"
            if settings.telegram_bot_token and settings.telegram_owner_id
            else "missing"
        )
        print(f"telegram {telegram_status}")
        print(f"openai {'configured' if settings.openai_api_key else 'missing'}")
    elif args.command == "status":
        if PID_FILE.exists():
            print(f"Wingman is running with PID {PID_FILE.read_text(encoding='utf-8').strip()}")
        else:
            print("Wingman is stopped")
    elif args.command == "stop":
        if not PID_FILE.exists():
            print("Wingman is already stopped")
            return
        pid = int(PID_FILE.read_text(encoding="utf-8"))
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        print(f"Stopped Wingman PID {pid}")
    elif args.command == "restart":
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text(encoding="utf-8"))
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
        start(no_browser=False)
    elif args.command == "update":
        branch = safe_update(get_settings())
        print(f"Updated branch {branch}")


if __name__ == "__main__":
    main()
