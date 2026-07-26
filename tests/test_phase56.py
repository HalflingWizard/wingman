import asyncio
import json
from types import SimpleNamespace

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.model_client import AVAILABLE_TOOLS, ModelClient
from wingman.models import User
from wingman.services import create_place
from wingman.tools import MemoryToolExecutor


def test_phase56_exposes_only_simplified_tools():
    names = {tool["name"] for tool in AVAILABLE_TOOLS}
    assert names == {
        "search_memories",
        "create_memory",
        "update_memory",
        "search_planning",
        "create_place",
        "create_saved_idea",
        "create_event",
        "create_reminder",
        "update_planning_item",
    }


def test_phase56_updates_owned_planning_record(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "A cafe")
        result = MemoryToolExecutor(session, user).execute(
            "update_planning_item",
            {
                "item_type": "place",
                "item_id": place.id,
                "changes": {"name": "A better cafe", "city": "Philadelphia"},
            },
        )
        assert result["updated"] is True
        assert result["verified"] is True
        assert result["title"] == "A better cafe"


def test_phase56_replays_duplicate_write_without_second_execution():
    settings = Settings(openai_api_key="test-key", openai_main_model="gpt-5-nano")
    client = ModelClient(settings)
    calls = []

    class FakeResponses:
        count = 0

        async def create(self, **kwargs):
            self.count += 1
            calls.append(kwargs)
            if self.count == 1:
                call = SimpleNamespace(
                    type="function_call",
                    name="create_memory",
                    arguments=json.dumps(
                        {
                            "action_id": None,
                            "statement": "The owner likes quiet cafes",
                            "memory_type": "preference",
                            "status": "confirmed",
                            "confidence": 1.0,
                            "importance": 3,
                        }
                    ),
                    call_id="one",
                )
                return SimpleNamespace(output=[call, call], output_text="", usage=None)
            return SimpleNamespace(output=[], output_text="Saved.", usage=None)

    client.client = SimpleNamespace(responses=FakeResponses())
    executed = []

    def execute(name, arguments):
        executed.append((name, arguments))
        return {"created": True, "verified": True}

    answer = asyncio.run(
        client.reply(
            [("user", "Remember that I like quiet cafes")],
            "Owner",
            "Person",
            "Static context",
            tool_executor=execute,
        )
    )
    assert answer == "Saved."
    assert len(executed) == 1
    assert calls[1]["input"][-1]["type"] == "function_call_output"
