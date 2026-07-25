from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database
from wingman.web import create_app


def test_dashboard_has_shared_visual_shell(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    page = TestClient(create_app(settings)).get("/")
    assert page.status_code == 200
    assert "app-shell" in page.text
    assert "fa-gauge-high" in page.text
    assert "summary-grid" in page.text
    assert "Workspace tools" in page.text


def test_all_dashboard_pages_use_shared_navigation(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    client = TestClient(create_app(settings))
    for path in (
        "/health",
        "/memories",
        "/planning",
        "/settings",
        "/system",
        "/conversations",
        "/api-calls",
        "/retrieval",
    ):
        page = client.get(path)
        assert page.status_code == 200
        assert "class='sidebar'" in page.text
        assert "fa-solid" in page.text
