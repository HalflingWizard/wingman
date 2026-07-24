from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import Message
from wingman.services import add_message, get_or_create_conversation, get_or_create_user
from wingman.web import create_app


def test_health_page_masks_secrets(tmp_path):
    database = f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(
        database_url=database,
        telegram_bot_token="secret-token",
        telegram_owner_id=42,
        openai_api_key="secret-key",
    )
    initialize_database(settings)
    response = TestClient(create_app(settings)).get("/health")
    assert response.status_code == 200
    assert "configured" in response.text
    assert "secret-token" not in response.text
    assert "secret-key" not in response.text


def test_messages_persist_and_authorized_user_is_separate(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = get_or_create_user(session, 42, "Owner")
        conversation = get_or_create_conversation(session, user)
        add_message(session, conversation, "user", "Hello", 1)
        add_message(session, conversation, "assistant", "Hi")
        assert session.query(Message).count() == 2
        assert get_or_create_user(session, 99).id != user.id
