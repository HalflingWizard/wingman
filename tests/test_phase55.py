from pathlib import Path

from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database
from wingman.prompting import load_prompt_configuration, load_prompt_sections
from wingman.web import create_app


def test_context_sections_are_persisted_and_used_by_preview(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        data_dir=str(tmp_path / "data"),
        prompt_file=str(tmp_path / "prompts" / "wingman.md"),
        user_name="Owner",
        primary_person_name="Person",
        timezone="America/New_York",
    )
    initialize_database(settings)
    client = TestClient(create_app(settings))

    response = client.post(
        "/context",
        data={
            "personality_safety": "Use a calm and direct tone.",
            "memory_planning": "Use saved records when they help.",
            "tool_orchestration": "Complete safe actions before replying.",
            "attachment_capabilities": "Describe only what is visible.",
            "custom_instructions": "Prefer short paragraphs.",
        },
    )

    assert response.status_code == 200
    configuration = load_prompt_configuration(settings)
    assert configuration["version_number"] == 1
    assert configuration["active"] is True
    assert load_prompt_sections(settings)["personality_safety"] == "Use a calm and direct tone."
    assert Path(settings.prompt_file).exists()

    preview = client.get("/context/preview")
    assert preview.status_code == 200
    assert "Use a calm and direct tone." in preview.text
    assert "Owner" in preview.text
    assert "America/New_York" in preview.text
    assert "search_saved_context" in preview.text


def test_context_save_increments_active_prompt_version(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        telegram_owner_id=42,
        data_dir=str(tmp_path / "data"),
        prompt_file=str(tmp_path / "prompts" / "wingman.md"),
    )
    initialize_database(settings)
    client = TestClient(create_app(settings))

    form = {
        "personality_safety": "First version",
        "memory_planning": "Memory rules",
        "tool_orchestration": "Tool rules",
        "attachment_capabilities": "Attachment rules",
        "custom_instructions": "",
    }
    client.post("/context", data=form)
    form["personality_safety"] = "Second version"
    client.post("/context", data=form)

    configuration = load_prompt_configuration(settings)
    assert configuration["version_number"] == 2
    assert configuration["sections"]["personality_safety"] == "Second version"
