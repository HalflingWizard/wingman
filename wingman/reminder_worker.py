"""One-time Telegram reminder delivery."""

import asyncio
from datetime import UTC, datetime

from aiogram import Bot

from wingman.config import Settings
from wingman.database import session_factory
from wingman.services import get_or_create_user, list_reminders, mark_reminder_delivered


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def run_reminder_worker(settings: Settings) -> None:
    if not settings.telegram_bot_token or settings.telegram_owner_id is None:
        return
    bot = Bot(settings.telegram_bot_token)
    try:
        while True:
            now = datetime.now(UTC)
            with session_factory(settings)() as session:
                user = get_or_create_user(session, settings.telegram_owner_id)
                reminders = list_reminders(session, user, True)
                due = [reminder for reminder in reminders if _as_utc(reminder.scheduled_at) <= now]
            for reminder in due:
                try:
                    await bot.send_message(settings.telegram_owner_id, f"Reminder {reminder.title}")
                except Exception:
                    continue
                with session_factory(settings)() as session:
                    mark_reminder_delivered(session, reminder.id)
            await asyncio.sleep(30)
    finally:
        await bot.session.close()
