from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.models import AgentRun, Memory, ToolExecution, User
from wingman.services import (
    create_agent_run,
    create_memory,
    delete_memory,
    get_or_create_conversation,
    get_owned_memory,
)
from wingman.tools import MemoryToolExecutor
from wingman.web import create_app


def phase2_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
    )


def test_memory_ownership_and_soft_delete(tmp_path):
    settings = phase2_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        owner = User(telegram_user_id=42, name="Owner")
        other = User(telegram_user_id=99, name="Other")
        session.add_all([owner, other])
        session.commit()
        memory = create_memory(session, owner, "Casa Verde is quiet", memory_type="food_clue")
        assert get_owned_memory(session, other, memory.id) is None
        delete_memory(session, owner, memory.id)
        assert session.get(Memory, memory.id).status == "deleted"


def test_tool_executor_validates_and_records(tmp_path):
    settings = phase2_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        owner = User(telegram_user_id=42, name="Owner")
        session.add(owner)
        session.commit()
        result = MemoryToolExecutor(session, owner).execute(
            "create_memory",
            {"statement": "She likes Solaris", "memory_type": "interest"},
        )
        assert result["status"] == "confirmed"
        assert session.query(ToolExecution).count() == 1
        try:
            MemoryToolExecutor(session, owner).execute(
                "update_memory", {"memory_id": "missing", "status": "confirmed"}
            )
        except ValueError:
            pass
        assert session.query(ToolExecution).count() == 2
        assert session.query(ToolExecution).filter_by(status="failed").count() == 1


def test_memory_web_create_edit_delete_and_agent_run(tmp_path):
    settings = phase2_settings(tmp_path)
    initialize_database(settings)
    client = TestClient(create_app(settings))
    response = client.post(
        "/memories",
        data={"statement": "She likes quiet places", "memory_type": "preference"},
    )
    assert response.status_code == 200
    assert "She likes quiet places" in response.text
    with session_factory(settings)() as session:
        user = session.query(User).filter_by(telegram_user_id=42).one()
        memory = session.query(Memory).one()
        conversation = get_or_create_conversation(session, user)
        run = create_agent_run(session, conversation, "test-model")
        assert session.get(AgentRun, run.id) is not None
    response = client.post(
        f"/memories/{memory.id}/update", data={"statement": "She likes calm places"}
    )
    assert "She likes calm places" in response.text
    response = client.post(f"/memories/{memory.id}/delete")
    assert "deleted" in response.text
