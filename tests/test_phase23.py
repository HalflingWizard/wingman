from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import User
from wingman.tools import MemoryToolExecutor


def test_planning_tools_create_partial_place_and_scheduled_records(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        executor = MemoryToolExecutor(session, user)

        place = executor.execute(
            "create_place",
            {
                "name": "Soyu",
                "address": "",
                "city": "",
                "description": "Known for Dubai chocolate",
                "place_type": "coffee shop",
                "atmosphere_tags": "cozy",
            },
        )
        assert place["created"] is True
        assert place["address"] == ""

        idea = executor.execute(
            "create_saved_idea",
            {
                "title": "Take her to Soyu",
                "reason": "She may enjoy the atmosphere",
                "place_id": place["place_id"],
            },
        )
        assert idea["created"] is True

        event = executor.execute(
            "create_event",
            {
                "title": "Coffee at Soyu",
                "start_at": "2026-08-01T15:00:00+00:00",
                "event_type": "date",
                "timezone": "UTC",
                "description": "Try the Dubai chocolate",
                "place_id": place["place_id"],
            },
        )
        assert event["created"] is True

        reminder = executor.execute(
            "create_reminder",
            {
                "title": "Confirm Soyu plans",
                "scheduled_at": "2026-07-31T12:00:00+00:00",
                "timezone": "UTC",
                "event_id": event["event_id"],
            },
        )
        assert reminder["created"] is True

        duplicate = executor.execute(
            "create_place",
            {
                "name": "soyu",
                "address": "",
                "city": "",
                "description": "",
                "place_type": "place",
                "atmosphere_tags": "",
            },
        )
        assert duplicate["duplicate"] is True


def test_search_planning_returns_owned_records(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        executor = MemoryToolExecutor(session, user)
        executor.execute(
            "create_place",
            {
                "name": "Casa Verde",
                "address": "Unknown",
                "city": "",
                "description": "Quiet and romantic",
                "place_type": "restaurant",
                "atmosphere_tags": "romantic",
            },
        )
        result = executor.execute("search_planning", {"query": "romantic", "top_k": 5})
        assert result["records"][0]["name"] == "Casa Verde"
