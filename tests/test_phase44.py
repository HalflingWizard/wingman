from types import SimpleNamespace

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import Memory, User
from wingman.retrieval import retrieve_memories
from wingman.services import create_memory
from wingman.telegram_bot import is_audio_document, is_video_document


def telegram_document(filename: str, mime_type: str):
    return SimpleNamespace(
        document=SimpleNamespace(file_name=filename, mime_type=mime_type),
        video=None,
        video_note=None,
        animation=None,
        audio=None,
    )


def test_telegram_documents_are_classified_by_mime_type_or_filename():
    assert is_video_document(telegram_document("clip.bin", "video/x-matroska"))
    assert is_video_document(telegram_document("clip.mkv", "application/octet-stream"))
    assert is_audio_document(telegram_document("recording.bin", "audio/mpeg"))
    assert not is_video_document(telegram_document("notes.pdf", "application/pdf"))


def test_high_importance_unrelated_memory_is_not_returned(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(settings)
    with session_factory(settings)() as session:
        owner = User(telegram_user_id=42, name="Owner")
        session.add(owner)
        session.commit()
        memory = create_memory(
            session,
            owner,
            "Private medical detail",
            memory_type="fact",
            importance=5,
        )
        results = retrieve_memories(session, owner, "transcribe a video")
        assert results == []
        assert session.get(Memory, memory.id).last_retrieved_at is None
