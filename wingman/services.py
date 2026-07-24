"""Small Phase 1 persistence and model services."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from wingman.models import Conversation, Message, User


def authorized_user(session: Session, owner_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_user_id == owner_id))


def get_or_create_user(session: Session, telegram_user_id: int, name: str = "") -> User:
    user = authorized_user(session, telegram_user_id)
    if user is None:
        user = User(telegram_user_id=telegram_user_id, name=name)
        session.add(user)
        session.flush()
    return user


def get_or_create_conversation(session: Session, user: User) -> Conversation:
    conversation = session.scalar(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at)
    )
    if conversation is None:
        conversation = Conversation(user=user)
        session.add(conversation)
        session.flush()
    return conversation


def add_message(
    session: Session,
    conversation: Conversation,
    sender: str,
    text: str,
    telegram_message_id: int | None = None,
) -> Message:
    message = Message(
        conversation=conversation,
        sender=sender,
        text=text,
        telegram_message_id=telegram_message_id,
    )
    session.add(message)
    session.commit()
    return message
