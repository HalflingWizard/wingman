"""Command line entry point."""

import argparse
import asyncio
import signal
import threading
import webbrowser
from pathlib import Path

import uvicorn

from wingman import __version__
from wingman.config import get_settings
from wingman.database import initialize_database
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
    initialize_database(settings)
    app = create_app(settings)

    def web_server() -> None:
        uvicorn.run(app, host=settings.web_host, port=settings.web_port, log_level="info")

    thread = threading.Thread(target=web_server, daemon=True)
    thread.start()
    address = f"http://{settings.web_host}:{settings.web_port}/health"
    print(f"Wingman {__version__} is running at {address}")
    if not no_browser:
        webbrowser.open(address)
    if settings.telegram_bot_token and settings.telegram_owner_id is not None:
        asyncio.run(run_bot(settings))
    else:
        print("Telegram is not configured. The health page remains available.")
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass


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
        print("Wingman status is available at the local health page")
    elif args.command in {"stop", "restart"}:
        print(f"{args.command} requires the Phase 6 supervisor")
    elif args.command == "update":
        print("Safe updates are planned for Phase 6")


if __name__ == "__main__":
    main()
