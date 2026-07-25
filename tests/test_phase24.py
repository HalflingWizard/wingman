from datetime import UTC, datetime

from wingman.database import initialize_database, session_factory
from wingman.models import User
from wingman.services import (
    create_event,
    create_place,
    delete_planning_record,
    save_telegram_planning_card,
)


def test_planning_cards_are_owned_and_deletable(tmp_path):
    settings_database = f"sqlite:///{tmp_path / 'test.db'}"
    from wingman.config import Settings

    settings = Settings(database_url=settings_database)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "Soyu", "", "", "A possible coffee date")
        event = create_event(
            session,
            user,
            "Coffee at Soyu",
            datetime(2026, 8, 1, 14, 0, tzinfo=UTC),
        )
        save_telegram_planning_card(session, user, "place", place.id, 42, 100)
        save_telegram_planning_card(session, user, "event", event.id, 42, 101)

        assert delete_planning_record(session, user, "place", place.id) == "Soyu"
        assert delete_planning_record(session, user, "event", event.id) == "Coffee at Soyu"
        assert place.status == "deleted"
        assert event.status == "cancelled"
