import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.model_client import ModelClient
from wingman.models import RetrievalLog, User
from wingman.services import (
    create_event,
    create_memory,
    create_place,
    create_reminder,
    create_saved_idea,
    get_or_create_conversation,
)
from wingman.tools import MemoryToolExecutor


def settings_for(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)


def search_arguments(query, categories, top_k=10, mode="search"):
    return {
        "query": query,
        "categories": categories,
        "top_k": top_k,
        "mode": mode,
        "city": None,
        "date_from": None,
        "date_to": None,
        "_query_embedding": [1.0, 0.0],
    }


def set_vector(record, vector=(1.0, 0.0)):
    record.embedding_json = json.dumps(list(vector))


@pytest.mark.parametrize(
    ("name", "description", "query"),
    [
        ("Mario's Corner", "Pizza restaurant the owner liked", "Where can we go for pizza?"),
        (
            "Green Garden",
            "Outdoor seating and comfortable for groups",
            "Somewhere good for six people where we can sit outside",
        ),
    ],
)
def test_phase510_semantic_place_retrieval_handles_direct_and_indirect_requests(
    tmp_path, name, description, query
):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, name, description=description)
        set_vector(place)
        session.commit()
        result = MemoryToolExecutor(session, user).execute(
            "search_saved_context",
            search_arguments(query, ["place"]),
        )
    assert [item["title"] for item in result["records"]] == [name]


def test_phase510_retrieves_each_saved_category_and_combines_cross_category_context(tmp_path):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        memory = create_memory(session, user, "Sarah is vegetarian.")
        place = create_place(
            session,
            user,
            "Green Garden",
            description="Vegetarian food and outdoor seating",
        )
        idea = create_saved_idea(session, user, "Visit the modern art museum")
        event = create_event(
            session,
            user,
            "Dinner with Sarah",
            datetime(2026, 8, 1, 19, tzinfo=UTC),
        )
        reminder = create_reminder(
            session,
            user,
            "Renew passport before September",
            datetime(2026, 8, 20, 9, tzinfo=UTC),
        )
        for record in (memory, place, idea, event, reminder):
            set_vector(record)
        session.commit()
        executor = MemoryToolExecutor(session, user)

        category_queries = {
            "memory": "Where should I take Sarah for dinner?",
            "idea": "What could we do this weekend?",
            "event": "What am I doing with Sarah this week?",
            "reminder": "Anything important before September?",
        }
        for category, query in category_queries.items():
            result = executor.execute(
                "search_saved_context",
                search_arguments(query, [category]),
            )
            assert result["records"][0]["category"] == category

        combined = executor.execute(
            "search_saved_context",
            search_arguments(
                "Help me plan dinner with Sarah",
                ["memory", "place", "event"],
            ),
        )
    assert {item["category"] for item in combined["records"]} == {
        "memory",
        "place",
        "event",
    }


def test_phase510_no_relevant_record_does_not_return_unrelated_context(tmp_path):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        place = create_place(session, user, "Tea House", description="Tea and pastries")
        set_vector(place, (0.0, 1.0))
        session.commit()
        result = MemoryToolExecutor(session, user).execute(
            "search_saved_context",
            search_arguments("Where should I go for sushi?", ["place"]),
        )
    assert result["records"] == []


def test_phase510_list_mode_returns_owned_records_without_literal_query_matching(tmp_path):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        create_place(session, user, "Tina's Cafe", city="Philadelphia")
        result = MemoryToolExecutor(session, user).execute(
            "search_saved_context",
            search_arguments("the owner's saved venues", ["place"], mode="list"),
        )
    assert [item["title"] for item in result["records"]] == ["Tina's Cafe"]


def test_phase510_model_forces_retrieval_then_preserves_user_input_and_grounds_answer(tmp_path):
    settings = settings_for(tmp_path).model_copy(
        update={"openai_api_key": "test-key", "openai_main_model": "gpt-5-nano"}
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        place = create_place(
            session,
            user,
            "Mario's Corner",
            description="A pizza restaurant the owner liked",
        )
        executor = MemoryToolExecutor(session, user, conversation=conversation)
        client = ModelClient(settings)
        calls = []
        embedded_batches = []

        class FakeResponses:
            async def create(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    return SimpleNamespace(
                        output=[
                            SimpleNamespace(
                                type="function_call",
                                name="search_saved_context",
                                arguments=json.dumps(
                                    {
                                        "query": "pizza restaurant for the owner",
                                        "categories": ["place"],
                                        "top_k": 5,
                                        "mode": "search",
                                        "city": None,
                                        "date_from": None,
                                        "date_to": None,
                                    }
                                ),
                                call_id="search-one",
                            )
                        ],
                        output_text="",
                        usage=None,
                    )
                tool_output = json.loads(kwargs["input"][-1]["output"])
                assert kwargs["input"][0]["role"] == "user"
                assert kwargs["input"][0]["content"] == "Where can we go for pizza?"
                assert tool_output["result"]["records"][0]["title"] == "Mario's Corner"
                return SimpleNamespace(
                    output=[],
                    output_text="Mario's Corner is one saved option you liked for pizza.",
                    usage=None,
                )

        client.client = SimpleNamespace(responses=FakeResponses())

        async def embed_batch(texts):
            embedded_batches.append(texts)
            return [[1.0, 0.0] for _ in texts]

        answer = asyncio.run(
            client.reply(
                [("user", "Where can we go for pizza?")],
                "Owner",
                "Sarah",
                tool_executor=executor.execute,
                embedding_batch_provider=embed_batch,
            )
        )
        session.refresh(place)
    assert "Mario's Corner" in answer
    assert calls[0]["tool_choice"] == {
        "type": "function",
        "name": "search_saved_context",
    }
    assert client.last_tool_trace[0]["name"] == "search_saved_context"
    assert place.embedding_json == json.dumps([1.0, 0.0])
    assert any("Mario's Corner" in batch[0] for batch in embedded_batches if batch)


def test_phase510_agent_can_refine_search_without_losing_previous_turn_context(tmp_path):
    settings = settings_for(tmp_path).model_copy(
        update={"openai_api_key": "test-key", "openai_main_model": "gpt-5-nano"}
    )
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        idea = create_saved_idea(session, user, "Try a neighborhood pizza crawl")
        set_vector(idea)
        session.commit()
        executor = MemoryToolExecutor(session, user)
        client = ModelClient(settings)
        calls = []

        class FakeResponses:
            async def create(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    return _tool_response("first", ["place"])
                if len(calls) == 2:
                    first_output = json.loads(kwargs["input"][-1]["output"])
                    assert first_output["result"]["records"] == []
                    return _tool_response("second", ["idea"])
                outputs = [
                    json.loads(item["output"])
                    for item in kwargs["input"]
                    if isinstance(item, dict) and item.get("type") == "function_call_output"
                ]
                assert len(outputs) == 2
                assert outputs[-1]["result"]["records"][0]["title"] == (
                    "Try a neighborhood pizza crawl"
                )
                return SimpleNamespace(
                    output=[],
                    output_text="You saved the idea of trying a neighborhood pizza crawl.",
                    usage=None,
                )

        def _tool_response(call_id, categories):
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="search_saved_context",
                        arguments=json.dumps(
                            {
                                "query": "pizza activity",
                                "categories": categories,
                                "top_k": 5,
                                "mode": "search",
                                "city": None,
                                "date_from": None,
                                "date_to": None,
                            }
                        ),
                        call_id=call_id,
                    )
                ],
                output_text="",
                usage=None,
            )

        client.client = SimpleNamespace(responses=FakeResponses())

        async def embed_query(_query):
            return [1.0, 0.0]

        answer = asyncio.run(
            client.reply(
                [("user", "What pizza-related activity had we considered?")],
                "Owner",
                "Sarah",
                tool_executor=executor.execute,
                query_embedding_provider=embed_query,
            )
        )
    assert "pizza crawl" in answer
    assert [trace["name"] for trace in client.last_tool_trace] == [
        "search_saved_context",
        "search_saved_context",
    ]


def test_phase510_update_search_supports_exact_and_ambiguous_record_resolution(tmp_path):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        corner = create_place(
            session,
            user,
            "Mario's Corner",
            description="Open until 10 PM",
        )
        bakery = create_place(session, user, "Mario's Bakery", description="Bakery hours")
        set_vector(corner)
        set_vector(bakery)
        session.commit()
        executor = MemoryToolExecutor(session, user)
        exact = executor.execute(
            "search_saved_context",
            search_arguments("Mario's Corner closing time", ["place"]),
        )
        ambiguous = executor.execute(
            "search_saved_context",
            search_arguments("Mario's opening time", ["place"]),
        )
        executor.execute(
            "update_planning_item",
            {
                "item_type": "place",
                "item_id": exact["records"][0]["record_id"],
                "changes": {"description": "Open until 11 PM"},
            },
        )
        session.refresh(corner)
    assert exact["records"][0]["title"] == "Mario's Corner"
    assert {item["title"] for item in ambiguous["records"]} == {
        "Mario's Corner",
        "Mario's Bakery",
    }
    assert corner.description == "Open until 11 PM"


def test_phase510_retrieval_diagnostics_record_routing_candidates_and_scores(tmp_path):
    settings = settings_for(tmp_path)
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        place = create_place(session, user, "Mario's Corner", description="Pizza restaurant")
        set_vector(place)
        session.commit()
        MemoryToolExecutor(session, user, conversation=conversation).execute(
            "search_saved_context",
            search_arguments("pizza dinner", ["place"]),
        )
        log = session.query(RetrievalLog).one()
        query = json.loads(log.query_json)
        candidates = json.loads(log.candidates_json)
    assert query["categories"] == ["place"]
    assert query["mode"] == "search"
    assert candidates[0]["title"] == "Mario's Corner"
    assert candidates[0]["relevance"]["semantic_similarity"] == 1.0
    assert candidates[0]["selected"] is True


def test_phase510_missing_required_retrieval_action_fails_explicitly():
    settings = Settings(openai_api_key="test-key", openai_main_model="gpt-5-nano")
    client = ModelClient(settings)

    class FakeResponses:
        async def create(self, **_kwargs):
            return SimpleNamespace(output=[], output_text="Skipped retrieval.", usage=None)

    client.client = SimpleNamespace(responses=FakeResponses())
    with pytest.raises(RuntimeError, match="required saved-context retrieval"):
        asyncio.run(
            client.reply(
                [("user", "Where can we go for pizza?")],
                "Owner",
                "Sarah",
                tool_executor=lambda _name, _arguments: {},
            )
        )


def test_phase510_existing_planning_tables_receive_embedding_columns(tmp_path):
    database_path = tmp_path / "old.db"
    with sqlite3.connect(database_path) as connection:
        for table_name in ("places", "saved_ideas", "events", "reminders"):
            connection.execute(f"CREATE TABLE {table_name} (id TEXT PRIMARY KEY)")
    settings = Settings(database_url=f"sqlite:///{database_path}")
    initialize_database(settings)
    with sqlite3.connect(database_path) as connection:
        for table_name in ("places", "saved_ideas", "events", "reminders"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}
            assert {"embedding_text", "embedding_json"} <= columns
