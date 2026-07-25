import json

from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.lifecycle import is_paused
from wingman.models import Memory, User
from wingman.system import export_user_data
from wingman.web import create_app


def test_context_page_edits_static_prompt(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        prompt_file=str(tmp_path / "wingman.md"),
    )
    initialize_database(settings)
    client = TestClient(create_app(settings))
    assert "Static context" in client.get("/context").text
    response = client.post("/context", data={"prompt": "Use a gentle tone."})
    assert response.status_code == 200
    assert "Use a gentle tone." in response.text


def test_settings_are_editable_without_revealing_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    client = TestClient(create_app(settings))
    response = client.post(
        "/settings",
        data={
            "telegram_bot_token": "new-token",
            "telegram_owner_id": "42",
            "openai_api_key": "new-key",
            "openai_main_model": "gpt-5-nano",
            "openai_summary_model": "gpt-5-nano",
            "user_name": "Odysseus",
            "primary_person_name": "Penelope",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 200
    assert "new-token" not in response.text
    assert (tmp_path / ".env").exists()


def test_system_pause_toggle_and_json_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        session.add(Memory(user_id=user.id, statement="Penelope likes pizza"))
        session.commit()
        payload = export_user_data(session, user)
    client = TestClient(create_app(settings))
    assert "Pause bot" in client.get("/system").text
    client.post("/system/bot/pause")
    assert is_paused(settings)
    assert "Resume bot" in client.get("/system").text
    response = client.post(
        "/system/import",
        files={
            "export_file": ("export.json", json.dumps(payload, default=str), "application/json")
        },
    )
    assert response.status_code == 200
    assert "Import completed" in response.text
