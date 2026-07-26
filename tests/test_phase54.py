import asyncio
import json
from types import SimpleNamespace

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.model_client import ModelClient
from wingman.models import Memory, User
from wingman.retrieval import retrieve_memories
from wingman.tools import MemoryToolExecutor


def test_hybrid_retrieval_rejects_name_only_matches_and_uses_cosine_similarity(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        semantic_match = Memory(
            user_id=user.id,
            statement="Chloe enjoys quiet neighborhood restaurants",
            embedding_json=json.dumps([1.0, 0.0]),
        )
        name_only_match = Memory(
            user_id=user.id,
            statement="Chloe likes silver accessories",
        )
        session.add_all([semantic_match, name_only_match])
        session.commit()

        results = retrieve_memories(
            session,
            user,
            "Chloe pizza place",
            query_vector=[1.0, 0.0],
        )

        assert [result.memory.id for result in results] == [semantic_match.id]
        assert results[0].semantic_similarity == 1.0


def test_memory_tool_passes_query_embedding_to_hybrid_retrieval(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = Memory(
            user_id=user.id,
            statement="She likes quiet restaurants",
            embedding_json=json.dumps([1.0, 0.0]),
        )
        session.add(memory)
        session.commit()

        result = MemoryToolExecutor(session, user).execute(
            "search_memories",
            {"query": "pizza place", "top_k": 5, "_query_embedding": [1.0, 0.0]},
        )

        assert result["memories"][0]["memory_id"] == memory.id


def test_model_client_requests_query_embedding_without_forcing_tool_choice():
    settings = Settings(openai_api_key="test-key", openai_main_model="gpt-5-nano")
    client = ModelClient(settings)
    calls = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="search_memories",
                            arguments=json.dumps({"query": "pizza place", "top_k": 5}),
                            call_id="call-search",
                        )
                    ],
                    output_text="",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=2),
                )
            return SimpleNamespace(
                output=[],
                output_text="No saved match was relevant.",
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    captured_arguments = []

    async def embed_query(query: str) -> list[float]:
        assert query == "pizza place"
        return [1.0, 0.0]

    def execute(name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured_arguments.append((name, arguments))
        return {"memories": []}

    answer = asyncio.run(
        client.reply(
            [("user", "Where is the pizza place we saved?")],
            "Owner",
            "Chloe",
            tool_executor=execute,
            query_embedding_provider=embed_query,
        )
    )

    assert answer == "No saved match was relevant."
    assert captured_arguments[0][1]["_query_embedding"] == [1.0, 0.0]
    assert calls[0]["tool_choice"] == "auto"
