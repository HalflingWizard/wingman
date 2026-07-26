from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import RuntimeErrorLog, User
from wingman.services import (
    add_message,
    get_or_create_conversation,
    record_runtime_error,
    reset_conversation,
)
from wingman.web import create_app


def test_new_chat_clears_history_but_keeps_owner_data(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        user_name="Owner",
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        add_message(session, conversation, "user", "old message")
        reset_conversation(session, user)
        assert conversation.messages == []
        assert session.query(User).filter_by(telegram_user_id=42).count() == 1


def test_runtime_errors_are_visible_in_logs(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        try:
            raise ValueError("transcription failed")
        except ValueError as error:
            record_runtime_error(session, user, "transcription", error, 17)
        assert session.query(RuntimeErrorLog).one().source_file
    response = TestClient(create_app(settings)).get("/logs")
    assert response.status_code == 200
    assert "Error history" in response.text
    assert "transcription failed" in response.text


def test_response_timeout_is_configurable(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        response_timeout_seconds=45,
    )
    assert settings.response_timeout_seconds == 45
