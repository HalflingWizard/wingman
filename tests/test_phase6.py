from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.lifecycle import is_paused, set_paused
from wingman.models import Memory, User
from wingman.retrieval import log_retrieval, retrieval_query, retrieve_memories
from wingman.services import get_or_create_conversation
from wingman.system import backup_database, export_user_data
from wingman.web import create_app


def phase6_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        data_dir=str(tmp_path / "data"),
    )


def test_database_export_and_backup(tmp_path):
    settings = phase6_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = Memory(user_id=user.id, statement="She likes silver accessories")
        session.add(memory)
        session.commit()
        payload = export_user_data(session, user)
        assert payload["memories"][0]["statement"] == "She likes silver accessories"
    backup = backup_database(settings)
    assert backup.exists()


def test_retrieval_inspector_shows_text_and_score_components(tmp_path):
    settings = phase6_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = Memory(
            user_id=user.id,
            statement="She likes silver accessories",
            embedding_text="She likes silver accessories",
        )
        session.add(memory)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        results = retrieve_memories(session, user, "silver accessories")
        log_retrieval(
            session,
            user,
            conversation,
            retrieval_query("silver accessories", user),
            results,
        )
    page = TestClient(create_app(settings)).get("/retrieval")
    assert "She likes silver accessories" in page.text
    assert "keyword_match" in page.text
    assert "semantic_similarity" in page.text
    assert "embedding_available" in page.text


def test_retrieval_ignores_stop_words_and_matches_related_word_forms(tmp_path):
    settings = phase6_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = Memory(user_id=user.id, statement="She likes silver accessories")
        session.add(memory)
        session.commit()
        results = retrieve_memories(session, user, "what type of jewelry")
        query = retrieval_query("what type of jewelry", user)
    assert results[0].memory.id == memory.id
    assert query["keywords"] == ["accessory"]


def test_bot_pause_state_is_persistent(tmp_path):
    settings = phase6_settings(tmp_path)
    assert not is_paused(settings)
    set_paused(settings, True)
    assert is_paused(settings)
    set_paused(settings, False)
    assert not is_paused(settings)
