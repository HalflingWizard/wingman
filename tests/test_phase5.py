from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.context_builder import build_context
from wingman.database import initialize_database, session_factory
from wingman.models import Event, Place, Reminder, SavedIdea, User
from wingman.services import (
    create_event,
    create_place,
    create_reminder,
    create_saved_idea,
    planning_context,
)
from wingman.web import create_app


def phase5_settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)


def test_planning_records_and_web_page(tmp_path):
    settings = phase5_settings(tmp_path)
    initialize_database(settings)
    client = TestClient(create_app(settings))
    response = client.post(
        "/planning/places",
        data={
            "name": "Casa Verde",
            "address": "125 Main Street",
            "city": "Boston",
            "description": "Quiet and romantic",
        },
    )
    assert response.status_code == 200
    assert "Casa Verde" in response.text
    client.post("/planning/ideas", data={"title": "Quiet dinner", "reason": "After exams"})
    client.post(
        "/planning/events",
        data={"title": "Dinner date", "start_at": "2030-01-02T19:00", "description": "Relaxed"},
    )
    client.post(
        "/planning/reminders",
        data={"title": "Confirm dinner", "scheduled_at": "2030-01-02T12:00"},
    )
    with session_factory(settings)() as session:
        assert session.query(Place).count() == 1
        assert session.query(SavedIdea).count() == 1
        assert session.query(Event).count() == 1
        assert session.query(Reminder).count() == 1
    dashboard = client.get("/")
    assert "/planning" in dashboard.text


def test_time_aware_planning_context(tmp_path):
    settings = phase5_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(
            session,
            user,
            "Casa Verde",
            description="Quiet restaurant",
            status="saved",
        )
        create_saved_idea(session, user, "Dinner after exams", "It is relaxing", place.id)
        create_event(
            session,
            user,
            "Dinner date",
            datetime.now(UTC) + timedelta(days=2),
            description="Calm evening",
        )
        create_reminder(session, user, "Confirm booking", datetime.now(UTC) + timedelta(days=1))
        places, ideas, events, reminders = planning_context(session, user)
        assert places[0].name == "Casa Verde"
        assert ideas[0].title == "Dinner after exams"
        assert events[0].title == "Dinner date"
        assert reminders[0].title == "Confirm booking"
        context = build_context(
            user,
            type("ConversationStub", (), {"messages": []})(),
            "Where should we go?",
            [],
            "UTC",
            places=places,
            ideas=ideas,
            events=events,
            reminders=reminders,
        )
        assert "Casa Verde" in context.dynamic_context
        assert "Dinner date" in context.dynamic_context
