"""Database setup for the initial domain records."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
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
        ConversationSummary,
        Event,
        Memory,
        MemoryNote,
        Message,
        PendingState,
        Place,
        Reminder,
        RetrievalLog,
        SavedIdea,
        SummaryUpdate,
        TelegramCard,
        TelegramPlanningCard,
        ToolExecution,
        User,
    )

    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(memories)"))}
            additions = {
                "embedding_text": "TEXT",
                "embedding_json": "TEXT",
                "last_retrieved_at": "DATETIME",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE memories ADD COLUMN {name} {definition}"))


def session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(settings), expire_on_commit=False)


def get_session(settings: Settings) -> Generator[Session, None, None]:
    session = session_factory(settings)()
    try:
        yield session
    finally:
        session.close()
