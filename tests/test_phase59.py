import os
from time import time

from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.database import initialize_database
from wingman.inbound import cleanup_orphaned_attachment_files
from wingman.runtime_log import record_runtime_output
from wingman.web import create_app


def test_phase59_removes_only_stale_wingman_temp_files(tmp_path):
    stale = tmp_path / "wingman-image-stale.jpg"
    fresh = tmp_path / "wingman-image-fresh.jpg"
    unrelated = tmp_path / "other-file.txt"
    for path in (stale, fresh, unrelated):
        path.write_text("temporary", encoding="utf-8")
    old_time = time() - 120
    os.utime(stale, (old_time, old_time))
    assert cleanup_orphaned_attachment_files(60, str(tmp_path)) == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()


def test_phase59_logs_page_has_bounded_live_log_controls(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    record_runtime_output("safe test line", operation="test")
    page = TestClient(create_app(settings)).get("/logs")
    assert page.status_code == 200
    assert "copy-live-log" in page.text
    assert "pause-live-log" in page.text
    assert "wrap-live-log" in page.text
    assert "Latest 100 lines" in page.text


def test_phase59_location_suggestions_return_timezone_without_external_lookup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    response = TestClient(create_app(settings)).get("/api/location-suggestions?q=New")
    assert response.status_code == 200
    assert response.json()["suggestions"] == [
        {"label": "New York, NY, USA", "timezone": "America/New_York"}
    ]


def test_phase59_planning_tabs_are_real_tab_links(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", telegram_owner_id=42)
    initialize_database(settings)
    page = TestClient(create_app(settings)).get("/planning?tab=places")
    assert page.status_code == 200
    assert "role='tablist'" in page.text
    assert "class='planning-tab active'" in page.text
    assert "class='planning-tab '" in page.text
