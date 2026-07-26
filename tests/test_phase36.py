import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

from wingman.config import Settings
from wingman.inbound import InboundAttachment, InboundMessage, cleanup_inbound_attachments
from wingman.model_client import ModelClient
from wingman.telegram_bot import supported_document_type


def test_document_allowlist_accepts_supported_extensions_and_rejects_unsafe_files():
    assert supported_document_type("report.pdf") == "application/pdf"
    assert supported_document_type("notes.MD") == "text/markdown"
    assert (
        supported_document_type("data.json", "application/custom+json") == "application/custom+json"
    )
    assert supported_document_type("program.exe") is None
    assert supported_document_type("archive.zip") is None
    assert supported_document_type("spreadsheet.xlsx") is None


def test_document_input_is_sent_as_a_file_without_raw_bytes_in_diagnostics(tmp_path):
    document_path = tmp_path / "notes.txt"
    document_bytes = b"Chloe likes quiet coffee shops."
    document_path.write_bytes(document_bytes)
    attachment = InboundAttachment(
        source_type="telegram_document",
        provider_file_id="document-1",
        filename="notes.txt",
        content_type="text/plain",
        local_path=str(document_path),
        size_bytes=len(document_bytes),
        estimated_characters=len(document_bytes.decode()),
    )
    client = ModelClient(Settings(openai_api_key="test-key"))
    calls = []

    class FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output=[],
                output_text="The document says Chloe likes quiet coffee shops.",
                usage=SimpleNamespace(input_tokens=30, output_tokens=9),
            )

    client.client = SimpleNamespace(responses=FakeResponses())
    answer = asyncio.run(
        client.reply(
            [("user", "What does this say?")],
            "Owner",
            "Person",
            attachments=(attachment,),
        )
    )

    assert answer.startswith("The document says")
    content = calls[0]["input"][-1]["content"]
    assert content[0] == {"type": "input_text", "text": "What does this say?"}
    assert content[1]["type"] == "input_file"
    assert content[1]["filename"] == "notes.txt"
    assert base64.b64decode(content[1]["file_data"]) == document_bytes
    snapshot = json.dumps(client.last_request_snapshot)
    assert document_bytes.decode() not in snapshot
    assert "file bytes omitted" in snapshot
    assert client.last_document_snapshot["documents"][0]["estimated_characters"] == len(
        document_bytes.decode()
    )


def test_document_metadata_is_preserved_and_temporary_file_is_cleaned(tmp_path):
    document_path = tmp_path / "data.json"
    document_path.write_text('{"favorite": "cats"}', encoding="utf-8")
    attachment = InboundAttachment(
        source_type="telegram_document",
        provider_file_id="document-2",
        filename="data.json",
        content_type="application/json",
        local_path=str(document_path),
        size_bytes=document_path.stat().st_size,
        estimated_characters=len(document_path.read_text(encoding="utf-8")),
    )
    inbound = InboundMessage("check this", "telegram_document", 12, (attachment,))

    assert inbound.attachments[0].filename == "data.json"
    assert inbound.attachments[0].estimated_characters == 20
    cleanup_inbound_attachments(inbound)
    assert not Path(attachment.local_path or "").exists()
