from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import User
from wingman.services import get_or_create_conversation
from wingman.tools import MemoryToolExecutor
from wingman.web import create_app


def test_telegram_service_write_is_immediately_visible_in_dashboard(tmp_path):
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
        result = MemoryToolExecutor(session, user, conversation=conversation).execute(
            "create_memory",
            {
                "statement": "She likes quiet coffee shops",
                "memory_type": "preference",
                "status": "observed",
                "confidence": 0.8,
                "importance": 3,
            },
        )
    client = TestClient(create_app(settings))
    page = client.get("/memories")
    dashboard = client.get("/")
    assert result["memory_id"] in page.text
    assert "She likes quiet coffee shops" in page.text
    assert "1 memories" in dashboard.text
    assert "Cache-Control" in page.headers
    assert "no-store" in page.headers["Cache-Control"]


def test_system_page_exposes_safe_database_scope_diagnostics(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    response = TestClient(create_app(settings)).get("/system")
    assert response.status_code == 200
    assert "Database diagnostics" in response.text
    assert str((tmp_path / "test.db").resolve()) in response.text
    assert "configured_owner_id" in response.text
