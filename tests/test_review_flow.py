from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient


def test_review_endpoint(monkeypatch):
    from app.main import app
    from app.api import routes

    class DummyReport:
        def __init__(self):
            self.id = uuid4()
            self.project_id = uuid4()
            self.section_key = "S-001"
            self.status = "DONE"
            self.report_json = {"modeled_issues": [], "general_comments": "ok"}
            self.created_at = datetime.now(timezone.utc)

    def fake_run(project_id: str, section_key: str):  # noqa: ARG001
        return DummyReport()

    monkeypatch.setattr("app.api.routes.run_compliance_review", fake_run)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "test-key", raising=False)

    client = TestClient(app)
    payload = {"project_id": str(uuid4()), "section_key": "S-001"}

    res = client.post("/v1/workflow/section/review", json=payload, headers={"X-API-Key": "test-key"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "DONE"
    assert body["report_json"]["general_comments"] == "ok"
