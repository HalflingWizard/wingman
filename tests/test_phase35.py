import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from wingman.config import Settings
from wingman.inbound import InboundAttachment, InboundMessage, cleanup_inbound_attachments
from wingman.model_client import ModelClient


def test_image_input_is_sent_as_multimodal_content_without_raw_bytes_in_diagnostics(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    attachment = InboundAttachment(
        source_type="telegram_image",
        provider_file_id="photo-1",
        filename="image.jpg",
        content_type="image/jpeg",
        local_path=str(image_path),
        size_bytes=image_path.stat().st_size,
        width=640,
        height=480,
    )
    client = ModelClient(Settings(openai_api_key="test-key"))
    calls = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output=[],
                output_text="I can see the image.",
                usage=SimpleNamespace(input_tokens=20, output_tokens=5),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    answer = asyncio.run(
        client.reply(
            [("user", "What do you notice?")],
            "Owner",
            "Person",
            attachments=(attachment,),
        )
    )

    assert answer == "I can see the image."
    content = calls[0]["input"][-1]["content"]
    assert content[0] == {"type": "input_text", "text": "What do you notice?"}
    assert content[1]["type"] == "input_image"
    assert content[1]["detail"] == "high"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    snapshot = json.dumps(client.last_request_snapshot)
    assert "fake-image-bytes" not in snapshot
    assert "image bytes omitted" in snapshot
    assert client.last_image_snapshot["images"][0]["width"] == 640


def test_image_only_message_preserves_attachment_metadata_and_cleans_temp_files(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image")
    attachment = InboundAttachment(
        source_type="telegram_image",
        provider_file_id="photo-1",
        content_type="image/jpeg",
        local_path=str(image_path),
        size_bytes=5,
        width=100,
        height=80,
    )
    inbound = InboundMessage("", "telegram_image", 10, (attachment,))
    assert inbound.text == ""
    assert inbound.attachments[0].size_bytes == 5
    assert inbound.attachments[0].width == 100
    cleanup_inbound_attachments(inbound)
    assert not Path(attachment.local_path or "").exists()


def test_empty_image_attachment_is_rejected_before_openai_request(tmp_path):
    image_path = tmp_path / "empty.jpg"
    image_path.write_bytes(b"")
    attachment = InboundAttachment(
        source_type="telegram_video_frame",
        provider_file_id="video-1",
        content_type="image/jpeg",
        local_path=str(image_path),
    )
    client = ModelClient(Settings(openai_api_key="test-key"))

    try:
        asyncio.run(
            client.reply(
                [("user", "Describe this video")],
                "Owner",
                "Person",
                attachments=(attachment,),
            )
        )
    except ValueError as exc:
        assert str(exc) == "Attachment is empty"
    else:
        raise AssertionError("Empty image attachments must be rejected")
