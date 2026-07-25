from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import Memory, MemoryNote, User
from wingman.services import get_open_pending_state, get_or_create_conversation
from wingman.tools import MemoryToolExecutor


def phase8_settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)


def test_memory_proposal_waits_for_confirmation_and_can_be_dismissed(tmp_path):
    settings = phase8_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        executor = MemoryToolExecutor(session, user, conversation=conversation)
        proposed = executor.execute(
            "propose_memory",
            {
                "statement": "Odysseus really likes Penelope's black dress",
                "memory_type": "observation",
                "status": "inferred",
                "confidence": 0.8,
                "importance": 3,
            },
        )
        assert session.query(Memory).count() == 0
        pending = get_open_pending_state(session, user, conversation)
        assert pending is not None
        assert pending.missing_information == "Odysseus really likes Penelope's black dress"
        assert proposed["status"] == "awaiting_confirmation"
        dismissed = executor.execute("dismiss_memory_proposal", {})
        assert dismissed["dismissed"] is True
        assert get_open_pending_state(session, user, conversation) is None


def test_confirmed_memory_closes_proposal_and_records_source_note(tmp_path):
    settings = phase8_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        executor = MemoryToolExecutor(
            session,
            user,
            conversation=conversation,
            source_message_id="source-message-id",
        )
        executor.execute(
            "propose_memory",
            {
                "statement": "Odysseus really likes Penelope's black dress",
                "memory_type": "observation",
                "status": "inferred",
                "confidence": 0.8,
                "importance": 3,
            },
        )
        result = executor.execute(
            "create_memory",
            {
                "statement": "Odysseus really likes Penelope's black dress",
                "memory_type": "observation",
                "status": "inferred",
                "confidence": 0.8,
                "importance": 3,
            },
        )
        memory = session.get(Memory, result["memory_id"])
        assert memory is not None
        note = session.query(MemoryNote).filter_by(memory_id=memory.id).one()
        assert note.source_message_id == "source-message-id"
        assert get_open_pending_state(session, user, conversation) is None
