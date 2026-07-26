import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from wingman.config import Settings
from wingman.inbound import InboundAttachment, InboundMessage, cleanup_inbound_attachments
from wingman.model_client import ModelClient
from wingman.telegram_bot import inspect_video


def test_video_frames_and_transcript_are_sent_as_ordered_multimodal_input(tmp_path):
    frames = []
    for index in range(5):
        frame_path = tmp_path / f"frame-{index + 1}.jpg"
        frame_path.write_bytes(f"frame-{index + 1}".encode())
        frames.append(
            InboundAttachment(
                source_type="telegram_video_frame",
                provider_file_id="video-1",
                filename=frame_path.name,
                content_type="image/jpeg",
                local_path=str(frame_path),
                frame_index=index + 1,
                duration_seconds=12.5,
            )
        )
    client = ModelClient(Settings(openai_api_key="test-key"))
    calls = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output=[],
                output_text="I found five frames and a transcript.",
                usage=SimpleNamespace(input_tokens=40, output_tokens=10),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    answer = asyncio.run(
        client.reply(
            [("user", "[Video transcript]\nShe enters a cafe.")],
            "Owner",
            "Person",
            attachments=tuple(frames),
        )
    )

    assert answer == "I found five frames and a transcript."
    content = calls[0]["input"][-1]["content"]
    assert content[0]["text"] == "[Video transcript]\nShe enters a cafe."
    assert [item["type"] for item in content[1:]] == ["input_image"] * 5
    assert client.last_video_snapshot["count"] == 5
    assert client.last_video_snapshot["frames"][0]["frame_index"] == 1
    assert "frame-1" in json.dumps(client.last_request_snapshot)
    assert "frame-1" not in json.dumps(client.last_request_snapshot["input"])
    cleanup_inbound_attachments(InboundMessage("", attachments=tuple(frames)))
    assert all(not Path(frame.local_path or "").exists() for frame in frames)


def test_video_probe_rejects_invalid_metadata(monkeypatch, tmp_path):
    video_path = tmp_path / "broken.mp4"
    video_path.write_bytes(b"not a video")

    async def fake_command(command, timeout_seconds):
        return b'{"format": {"duration": "not-a-number"}}', b""

    monkeypatch.setattr("wingman.telegram_bot.run_media_command", fake_command)
    try:
        asyncio.run(inspect_video(str(video_path), Settings()))
    except RuntimeError as exc:
        assert str(exc) == "Could not read video metadata"
    else:
        raise AssertionError("Invalid video metadata should fail")
