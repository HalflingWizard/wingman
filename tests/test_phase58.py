from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import User
from wingman.services import create_place
from wingman.web import create_app


def phase58_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        user_name="Owner",
        timezone="America/New_York",
    )


def test_phase58_planning_tabs_search_edit_and_hard_delete(tmp_path):
    settings = phase58_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "Quiet Cafe", city="Philadelphia")
        place_id = place.id
    client = TestClient(create_app(settings))

    page = client.get("/planning?tab=places&q=quiet")
    assert page.status_code == 200
    assert "Quiet Cafe" in page.text
    assert "Saved ideas" in page.text

    edited = client.post(
        f"/planning/places/{place_id}/edit",
        data={
            "name": "Updated Cafe",
            "address": "1 Main St",
            "city": "Philadelphia",
            "description": "Good",
        },
    )
    assert edited.status_code == 200
    with session_factory(settings)() as session:
        assert session.get(type(place), place_id).name == "Updated Cafe"

    deleted = client.post(f"/planning/places/{place_id}/delete")
    assert deleted.status_code == 200
    with session_factory(settings)() as session:
        assert session.get(type(place), place_id) is None


def test_phase58_settings_persists_selected_location_and_timezone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = phase58_settings(tmp_path)
    initialize_database(settings)
    client = TestClient(create_app(settings))
    page = client.get("/settings")
    assert page.status_code == 200
    assert "name='location'" in page.text
    assert "America/New_York" in page.text

    saved = client.post(
        "/settings",
        data={
            "telegram_owner_id": "42",
            "user_name": "Owner",
            "primary_person_name": "Person",
            "timezone": "America/Los_Angeles",
            "location": "Los Angeles, CA, USA",
        },
    )
    assert saved.status_code == 200
    assert "Los Angeles, CA, USA" in saved.text
    assert "America/Los_Angeles" in saved.text
