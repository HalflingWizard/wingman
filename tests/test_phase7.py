import asyncio
import json
from types import SimpleNamespace

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.model_client import ModelClient
from wingman.models import Memory, User
from wingman.tools import MemoryToolExecutor


def phase7_settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)


def test_search_memory_tool_returns_owned_text_and_notes(tmp_path):
    settings = phase7_settings(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Odysseus")
        session.add(user)
        session.commit()
        memory = Memory(user_id=user.id, statement="Penelope likes silver accessories")
        session.add(memory)
        session.commit()
        result = MemoryToolExecutor(session, user).execute(
            "search_memories", {"query": "what jewelry does she like"}
        )
    assert result["memories"][0]["memory_id"] == memory.id
    assert result["memories"][0]["statement"] == "Penelope likes silver accessories"


def test_model_client_runs_application_controlled_tool_loop():
    settings = Settings(openai_api_key="test-key", openai_main_model="gpt-5-nano")
    client = ModelClient(settings)
    calls = []

    class FakeResponses:
        response_count = 0

        async def create(self, **kwargs):
            calls.append(kwargs)
            self.response_count += 1
            if self.response_count == 1:
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="search_saved_context",
                            arguments=json.dumps(
                                {
                                    "query": "jewelry",
                                    "categories": ["memory"],
                                    "top_k": 5,
                                    "mode": "search",
                                    "city": None,
                                    "date_from": None,
                                    "date_to": None,
                                }
                            ),
                            call_id="call-1",
                        )
                    ],
                    output_text="",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=2),
                )
            return SimpleNamespace(
                output=[],
                output_text="She likes silver accessories.",
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    executed = []

    def execute(name, arguments):
        executed.append((name, arguments))
        return {"records": [{"content": "She likes silver accessories"}]}

    answer = asyncio.run(
        client.reply(
            [("user", "What jewelry does she like?")],
            "Odysseus",
            "Penelope",
            "Static context",
            "Dynamic context",
            tool_executor=execute,
        )
    )
    assert answer == "She likes silver accessories."
    assert executed == [
        (
            "search_saved_context",
            {
                "query": "jewelry",
                "categories": ["memory"],
                "top_k": 5,
                "mode": "search",
                "city": None,
                "date_from": None,
                "date_to": None,
            },
        )
    ]
    assert "tools" in calls[0]
    assert calls[1]["input"][-1]["type"] == "function_call_output"
    assert client.last_request_snapshot["model"] == "gpt-5-nano"
    assert client.last_request_snapshot["reasoning"] == {"effort": "low", "summary": "auto"}
    assert client.last_request_snapshot["text"] == {"verbosity": "low"}
    assert client.last_request_snapshot["store"] is False
    assert client.last_request_snapshot["tools"][0]["parameters"]["required"] == [
        "query",
        "categories",
        "top_k",
        "mode",
        "city",
        "date_from",
        "date_to",
    ]
