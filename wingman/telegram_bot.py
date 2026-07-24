"""Telegram polling and owner authorization."""

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message as TelegramMessage

from wingman.config import Settings
from wingman.database import session_factory
from wingman.model_client import ModelClient
from wingman.services import add_message, get_or_create_conversation, get_or_create_user


def build_dispatcher(settings: Settings) -> Dispatcher:
    dispatcher = Dispatcher()
    router = Router()
    sessions = session_factory(settings)
    model_client = ModelClient(settings) if settings.openai_api_key else None

    @router.message(CommandStart())
    async def start(message: TelegramMessage) -> None:
        if message.from_user is None or message.from_user.id != settings.telegram_owner_id:
            return
        await message.answer("I am ready. Tell me what is on your mind.")

    @router.message()
    async def chat(message: TelegramMessage) -> None:
        if message.from_user is None or message.from_user.id != settings.telegram_owner_id:
            return
        if not message.text:
            return
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id, message.from_user.full_name)
            conversation = get_or_create_conversation(session, user)
            add_message(session, conversation, "user", message.text, message.message_id)
            history = [(item.sender, item.text) for item in conversation.messages]
        if model_client is None:
            await message.answer("I am connected, but the OpenAI API key is not configured yet.")
            return
        try:
            answer = await model_client.reply(
                history, settings.user_name, settings.primary_person_name
            )
        except Exception:
            await message.answer("I ran into a problem while replying. Please try again.")
            return
        with sessions() as session:
            user = get_or_create_user(session, message.from_user.id)
            conversation = get_or_create_conversation(session, user)
            add_message(session, conversation, "assistant", answer)
        await message.answer(answer)

    dispatcher.include_router(router)
    return dispatcher


async def run_bot(settings: Settings) -> None:
    if not settings.telegram_bot_token or settings.telegram_owner_id is None:
        raise RuntimeError("Telegram bot token and owner ID are required")
    bot = Bot(settings.telegram_bot_token)
    try:
        await build_dispatcher(settings).start_polling(bot)
    finally:
        await bot.session.close()
