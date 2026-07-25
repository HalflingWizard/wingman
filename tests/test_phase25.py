from wingman.config import Settings
from wingman.database import initialize_database, session_factory
from wingman.inbound import InboundAttachment, InboundMessage, cleanup_inbound_attachments
from wingman.models import MessageAttachment, User
from wingman.services import add_message, get_or_create_conversation, save_message_attachments


def test_attachment_metadata_is_linked_without_audio_bytes(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(settings)
    with session_factory(settings)() as session:
        user = User(telegram_user_id=42, name="Owner")
        session.add(user)
        session.commit()
        conversation = get_or_create_conversation(session, user)
        message = add_message(session, conversation, "user", "A voice transcript")
        inbound = InboundMessage(
            "A voice transcript",
            attachments=(InboundAttachment("telegram_voice", "voice-1"),),
        )
        records = save_message_attachments(session, message.id, inbound.attachments)
        assert records[0].processing_status == "processed"
        assert session.query(MessageAttachment).count() == 1
        assert not hasattr(records[0], "audio")


def test_cleanup_removes_only_explicit_temporary_paths(tmp_path):
    temporary_file = tmp_path / "voice.ogg"
    temporary_file.write_bytes(b"audio")
    message = InboundMessage(
        "transcript",
        attachments=(
            InboundAttachment("telegram_voice", "voice-1", local_path=str(temporary_file)),
        ),
    )
    cleanup_inbound_attachments(message)
    assert not temporary_file.exists()
