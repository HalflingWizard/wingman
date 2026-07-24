"""Database setup for the initial domain records."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from wingman.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings) -> Engine:
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args)


def initialize_database(settings: Settings) -> None:
    from wingman.models import (  # noqa: F401
        AgentRun,
        Conversation,
        Memory,
        Message,
        TelegramCard,
        ToolExecution,
        User,
    )

    Base.metadata.create_all(make_engine(settings))


def session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(settings), expire_on_commit=False)


def get_session(settings: Settings) -> Generator[Session, None, None]:
    session = session_factory(settings)()
    try:
        yield session
    finally:
        session.close()
