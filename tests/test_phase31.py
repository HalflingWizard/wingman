from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import Conversation, User
from wingman.services import (
    action_ledger,
    confirm_action_items,
    create_action_group,
    mark_action_item,
    register_action_items,
)
from wingman.tools import MemoryToolExecutor


def test_action_ledger_tracks_group_confirmation_and_completion(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        conversation = Conversation(user_id=user.id)
        session.add(conversation)
        session.commit()
        group = create_action_group(session, user, conversation, "message-1")
        register_action_items(
            session,
            user,
            group,
            [
                {
                    "action_id": "cats",
                    "action_type": "memory",
                    "statement": "Penelope likes cats",
                    "requires_confirmation": False,
                },
                {
                    "action_id": "hello-kitty",
                    "action_type": "memory",
                    "statement": "Penelope thinks Hello Kitty is cute",
                    "requires_confirmation": True,
                },
            ],
        )
        assert action_ledger(session, user, conversation)["continue_required"] is True
        confirmed = confirm_action_items(session, user, conversation, ["hello-kitty"])
        assert confirmed["confirmed"] == ["hello-kitty"]
        mark_action_item(session, user, "cats", "completed", {"memory_id": "memory-1"})
        mark_action_item(session, user, "hello-kitty", "completed", {"memory_id": "memory-2"})
        final_ledger = action_ledger(session, user, conversation)
    assert final_ledger["continue_required"] is False
    assert final_ledger["items"] == []


def test_memory_executor_accepts_action_id_without_persisting_it(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        result = MemoryToolExecutor(session, user).execute(
            "create_memory",
            {
                "action_id": "pizza",
                "statement": "Penelope likes pizza",
                "memory_type": "preference",
                "status": "observed",
                "confidence": 0.9,
                "importance": 3,
            },
        )
    assert result["status"] == "observed"
