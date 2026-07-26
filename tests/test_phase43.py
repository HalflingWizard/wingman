from fastapi.testclient import TestClient

from wingman.config import Settings
from wingman.runtime_log import record_runtime_output
from wingman.web import create_app


def test_live_runtime_output_is_available_from_dashboard_api(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    record_runtime_output("phase 4.3 test line", operation="test")

    response = TestClient(create_app(settings)).get("/api/logs/live")

    assert response.status_code == 200
    assert any(line["message"] == "phase 4.3 test line" for line in response.json()["lines"])


def test_live_runtime_output_is_bounded():
    for index in range(130):
        record_runtime_output(f"line {index}", operation="test")

    from wingman.runtime_log import recent_runtime_output

    lines = recent_runtime_output()
    assert len(lines) == 100
    assert lines[0]["message"] == "line 30"
    assert lines[-1]["message"] == "line 129"
