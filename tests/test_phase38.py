from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database
from wingman.web import create_app


def test_dashboard_shows_loaded_revision_and_usage_page(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        user_name="Owner",
    )
    initialize_database(settings)
    client = TestClient(create_app(settings))

    dashboard = client.get("/")
    assert "Loaded repository version" in dashboard.text
    assert "Commit" in dashboard.text
    assert "/usage" in dashboard.text

    usage = client.get("/usage")
    assert usage.status_code == 200
    assert "Cost and usage" in usage.text
    assert "No usage recorded yet" in usage.text
