from datetime import UTC, datetime

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import Memory, User
from wingman.services import (
    create_event,
    create_place,
    get_telegram_card_context,
    save_telegram_planning_card,
)
from wingman.time_ranges import resolve_date_range
from wingman.tools import MemoryToolExecutor


def test_phase57_resolves_last_week_in_configured_timezone():
    start, end = resolve_date_range(
        "what did we do last week",
        "America/New_York",
        now=datetime(2026, 7, 26, 15, tzinfo=UTC),
    )
    assert start == datetime(2026, 7, 13, 4, tzinfo=UTC)
    assert end == datetime(2026, 7, 20, 4, tzinfo=UTC)


def test_phase57_unified_search_accepts_date_filters(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = Memory(
            user_id=user.id,
            statement="Owner likes quiet cafes",
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        session.add(memory)
        session.commit()
        result = MemoryToolExecutor(session, user, timezone="America/New_York").execute(
            "search_saved_context",
            {
                "query": "quiet cafes",
                "categories": ["memory"],
                "top_k": 5,
                "mode": "search",
                "city": None,
                "date_from": "2026-07-13T00:00:00-04:00",
                "date_to": "2026-07-20T00:00:00-04:00",
            },
        )
        assert result["records"][0]["record_id"] == memory.id


def test_phase57_unified_search_filters_by_type_and_city(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "Quiet Cafe", city="Philadelphia")
        create_event(
            session,
            user,
            "Dinner",
            datetime(2026, 8, 1, 20, tzinfo=UTC),
            place_id=place.id,
        )
        result = MemoryToolExecutor(session, user).execute(
            "search_saved_context",
            {
                "query": "cafe",
                "categories": ["place"],
                "top_k": 10,
                "mode": "search",
                "city": "Philadelphia",
                "date_from": None,
                "date_to": None,
            },
        )
        assert [record["record_id"] for record in result["records"]] == [place.id]


def test_phase57_card_context_returns_owned_record_details(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "Quiet Cafe", city="Philadelphia")
        save_telegram_planning_card(session, user, "place", place.id, 42, 9001)
        context = get_telegram_card_context(session, user, 42, 9001)
        assert context == {
            "card_type": "place",
            "record_id": place.id,
            "name": "Quiet Cafe",
            "address": "",
            "city": "Philadelphia",
            "description": "",
            "place_type": "place",
        }
