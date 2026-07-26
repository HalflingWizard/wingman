import asyncio
import json
from types import SimpleNamespace

from wingman.config import Settings
from wingman.inbound import InboundAttachment, InboundMessage
from wingman.model_client import ModelClient, mandatory_retrieval_tool


def test_every_user_turn_selects_memory_search_first():
    assert mandatory_retrieval_tool([("user", "Hello")]) == "search_memories"
    assert mandatory_retrieval_tool([("user", "Please use my saved memories")]) == (
        "search_memories"
    )
    assert mandatory_retrieval_tool([("assistant", "Hello")]) is None


def test_inbound_message_supports_multiple_temporary_attachments():
    first = InboundAttachment("telegram_voice", "voice-1", local_path="/tmp/voice-1")
    second = InboundAttachment("telegram_image", "image-1", local_path="/tmp/image-1")
    message = InboundMessage("transcribed text", "telegram_voice", 12, (first, second))
    assert message.has_temporary_input
    assert len(message.attachments) == 2


def test_model_request_allows_multiple_tool_calls():
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
                            arguments=json.dumps({"query": "jewelry", "top_k": 5}),
                            call_id="call-1",
                        ),
                        SimpleNamespace(
                            type="function_call",
                            name="search_memories",
                            arguments=json.dumps({"query": "restaurants", "top_k": 5}),
                            call_id="call-2",
                        ),
                    ],
                    output_text="",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=2),
                )
            return SimpleNamespace(
                output=[],
                output_text="Done.",
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    executed = []

    def execute(name, arguments):
        executed.append((name, arguments))
        return {"ok": True}

    answer = asyncio.run(
        client.reply(
            [("user", "search both")],
            "Odysseus",
            "Penelope",
            tool_executor=execute,
        )
    )
    assert answer == "Done."
    assert len(executed) == 2
    assert calls[0]["parallel_tool_calls"] is True
    assert calls[0]["tool_choice"] == {"type": "function", "name": "search_memories"}


def test_explicit_memory_request_forces_first_search_then_returns_to_auto():
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
                            arguments=json.dumps({"query": "Chloe", "top_k": 5}),
                            call_id="call-search",
                        )
                    ],
                    output_text="",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=2),
                )
            return SimpleNamespace(
                output=[],
                output_text="I found the relevant saved detail.",
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    answer = asyncio.run(
        client.reply(
            [("user", "Use my saved memories about Chloe")],
            "Owner",
            "Chloe",
            tool_executor=lambda _name, _arguments: {"memories": []},
        )
    )

    assert answer == "I found the relevant saved detail."
    assert calls[0]["tool_choice"] == {"type": "function", "name": "search_memories"}
    assert calls[1]["tool_choice"] == "auto"


def test_model_client_transcribes_voice_without_persisting_audio():
    settings = Settings(openai_api_key="test-key")
    client = ModelClient(settings)

    class FakeTranscriptions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "gpt-4o-mini-transcribe"
            assert kwargs["file"] == ("voice.ogg", b"audio")
            return SimpleNamespace(text="A transcribed message")

    client.client = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    transcript = asyncio.run(client.transcribe(b"audio", "voice.ogg", "gpt-4o-mini-transcribe"))
    assert transcript == "A transcribed message"
    assert client.last_transcription_snapshot["audio_retained"] is False
    assert "audio" not in client.last_transcription_snapshot
