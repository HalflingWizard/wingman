"""Normalized inbound message types for text and future temporary attachments."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class InboundAttachment:
    """A temporary input file that is deleted after processing."""

    source_type: str
    provider_file_id: str
    filename: str | None = None
    content_type: str | None = None
    local_path: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))


@dataclass(frozen=True)
class InboundMessage:
    """A provider-neutral message envelope for the conversation pipeline."""

    text: str
    source_type: str = "text"
    provider_message_id: int | None = None
    attachments: tuple[InboundAttachment, ...] = ()

    @property
    def has_temporary_input(self) -> bool:
        return bool(self.attachments)


def cleanup_inbound_attachments(message: InboundMessage) -> None:
    """Delete only explicitly created local attachment files."""
    for attachment in message.attachments:
        if attachment.local_path:
            Path(attachment.local_path).unlink(missing_ok=True)
