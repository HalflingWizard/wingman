from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.context_builder import build_context
from wingman.database import initialize_database, session_factory
from wingman.models import Conversation, Memory, MemoryNote, User
from wingman.prompting import load_prompt
from wingman.retrieval import retrieval_context_usage, retrieve_memories
from wingman.web import create_app


def test_editable_prompt_and_retrieved_notes_reach_context(tmp_path):
    prompt_file = tmp_path / "style.md"
    prompt_file.write_text("Use a calm, playful tone.", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        prompt_file=str(prompt_file),
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Matt")
        session.add(user)
        session.commit()
        conversation = Conversation(user_id=user.id)
        memory = Memory(user_id=user.id, statement="Chloe likes silver accessories")
        session.add_all([conversation, memory])
        session.commit()
        session.add(
            MemoryNote(
                memory_id=memory.id,
                text="She wore them at Sara's birthday.",
                note_type="evidence",
                source_message_id="source-1",
            )
        )
        session.commit()
        results = retrieve_memories(session, user, "jewelry")
        context = build_context(
            user,
            conversation,
            "jewelry",
            results,
            "UTC",
            prompt_text=load_prompt(settings),
        )
    assert "Use a calm, playful tone." in context.static_context
    assert "Sara's birthday" in context.dynamic_context
    assert "source-1" in context.dynamic_context
    usage = retrieval_context_usage(results, "Silver accessories would fit her style.")
    assert usage["mentioned_memory_ids"] == [memory.id]


def test_retrieval_inspector_uses_code_panels(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )
    initialize_database(settings)
    page = TestClient(create_app(settings)).get("/retrieval")
    assert "code-panel" in page.text
    assert "copyCode" in page.text
    assert "json-key" in page.text
