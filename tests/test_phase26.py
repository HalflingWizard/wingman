from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import User
from wingman.services import add_message, create_memory, get_or_create_conversation
from wingman.web import create_app


def test_dashboard_uses_consistent_refined_layout(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        create_memory(session, user, "A useful detail")
        conversation = get_or_create_conversation(session, user)
        add_message(session, conversation, "user", "Hello")
    client = TestClient(create_app(settings))

    memories = client.get("/memories").text
    planning = client.get("/planning").text
    conversations = client.get("/conversations").text

    assert "class='record-statement'" in memories
    assert "<textarea name='statement'" in memories
    assert "class='planning-grid'" in planning
    assert "class='item-list'" in planning
    assert "class='conversation-list'" in conversations
    assert "message-user" in conversations
