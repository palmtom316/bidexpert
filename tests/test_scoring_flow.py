from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient


def test_scoring_endpoint(monkeypatch):
    from app.main import app
    from app.api import routes

    class DummyScore:
        def __init__(self):
            self.id = uuid4()
            self.project_id = uuid4()
            self.score_total = 88.5
            self.details_json = {"sections": 3}
            self.created_at = datetime.now(timezone.utc)

    def fake_score(project_id: str):  # noqa: ARG001
        return DummyScore()

    monkeypatch.setattr("app.api.routes.run_scoring_service", fake_score)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "test-key", raising=False)

    client = TestClient(app)
    payload = {"project_id": str(uuid4())}

    res = client.post("/v1/workflow/scoring/calculate", json=payload, headers={"X-API-Key": "test-key"})
    assert res.status_code == 200
    body = res.json()
    assert body["score_total"] == 88.5
    assert body["details_json"]["sections"] == 3
