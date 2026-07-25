from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.context_builder import build_context
from wingman.database import initialize_database, session_factory
from wingman.model_client import ModelClient
from wingman.models import Memory, User
from wingman.services import (
    add_memory_note,
    add_message,
    create_agent_run,
    create_pending_state,
    finish_agent_run,
    get_open_pending_state,
    get_or_create_conversation,
    get_or_create_summary,
    save_summary,
)
from wingman.web import create_app


def phase4_settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)


def test_note_edit_and_remove_from_web(tmp_path):
    settings = phase4_settings(tmp_path)
    initialize_database(settings)
    client = TestClient(create_app(settings))
    client.post("/memories", data={"statement": "She likes books", "memory_type": "interest"})
    with session_factory(settings)() as session:
        user = session.query(User).filter_by(telegram_user_id=42).one()
        memory = session.query(Memory).one()
        note = add_memory_note(session, user, memory.id, "She mentioned Solaris")
    response = client.post(
        f"/notes/{note.id}/update",
        data={"note_text": "She recommended Solaris", "note_type": "evidence"},
    )
    assert "She recommended Solaris" in response.text
    response = client.post(f"/notes/{note.id}/delete")
    assert "She recommended Solaris" not in response.text


def test_dashboard_and_full_api_call_inspector(tmp_path):
    settings = phase4_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        run = create_agent_run(
            session,
            conversation,
            "test-model",
            '{"system_prompt":"system","user_prompt":"hello","context_added":"memory"}',
        )
        finish_agent_run(session, run.id, "completed", response_snapshot="answer")
    client = TestClient(create_app(settings))
    dashboard = client.get("/")
    assert "/memories" in dashboard.text
    assert "/api-calls" in dashboard.text
    calls = client.get("/api-calls")
    assert "system_prompt" in calls.text
    assert "context_added" in calls.text
    assert "answer" in calls.text


def test_summary_pending_state_and_context_budget(tmp_path):
    settings = phase4_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        message = add_message(session, conversation, "user", "A long conversation detail")
        summary = get_or_create_summary(session, conversation)
        save_summary(
            session,
            conversation,
            "The user is planning a calm date.",
            [message.id],
            message.id,
        )
        state = create_pending_state(
            session,
            user,
            conversation,
            "complete_place",
            "address",
            "What is the address?",
            datetime.now(UTC) + timedelta(hours=1),
        )
        assert get_open_pending_state(session, user, conversation).id == state.id
        context = build_context(
            user,
            conversation,
            "What should I do?",
            [],
            "UTC",
            summary=summary,
            pending_state=state,
            token_budget=500,
        )
        assert "calm date" in context.dynamic_context
        assert "What is the address" in context.dynamic_context
        state.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        assert get_open_pending_state(session, user, conversation) is None


def test_responses_payload_separates_static_dynamic_and_history():
    settings = Settings(openai_api_key="test-key")
    client = ModelClient(settings)
    calls = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text="Use the silver accessories memory.",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    import asyncio

    answer = asyncio.run(
        client.reply(
            [("user", "what accessories should I consider?")],
            "Odysseus",
            "Penelope",
            "Static profile and safety rules.",
            "Relevant saved context\n- She likes silver accessories.",
        )
    )
    assert answer.startswith("Use the silver")
    request = calls[0]
    assert request["instructions"].startswith("Static profile and safety rules.")
    assert "search_memories" in request["instructions"]
    assert request["instructions"].endswith(
        "The user's name is Odysseus. The person discussed is Penelope."
    )
    assert request["input"][0]["role"] == "developer"
    assert "silver accessories" in request["input"][0]["content"]
    assert request["input"][1] == {
        "role": "user",
        "content": "what accessories should I consider?",
    }
