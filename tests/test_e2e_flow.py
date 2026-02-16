from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from app.schemas.contracts import DraftGenerationResponse


def test_generation_review_scoring_flow(monkeypatch):
    from app.main import app

    class DummyReport:
        def __init__(self):
            self.id = uuid4()
            self.project_id = uuid4()
            self.section_key = "S-001"
            self.status = "PASS"
            self.report_json = {"modeled_issues": []}
            self.created_at = datetime.now(timezone.utc)

    class DummyScore:
        def __init__(self):
            self.id = uuid4()
            self.project_id = uuid4()
            self.score_total = 95.0
            self.details_json = {"items": []}
            self.created_at = datetime.now(timezone.utc)

    def fake_generate(*args, **kwargs):  # noqa: ARG001
        return DraftGenerationResponse(
            generated_text="hello",
            evidence_ids=["e1"],
            status="SUCCESS",
            missing_sentences=[],
            coverage=1.0,
            warnings=[],
        )

    def fake_review(project_id: str, section_key: str):  # noqa: ARG001
        return DummyReport()

    def fake_score(project_id: str):  # noqa: ARG001
        return DummyScore()

    monkeypatch.setattr("app.api.routes.generate_draft_with_retrieval", fake_generate)
    monkeypatch.setattr("app.api.routes.run_compliance_review", fake_review)
    monkeypatch.setattr("app.api.routes.run_scoring_service", fake_score)

    client = TestClient(app)

    g_res = client.post(
        "/v1/generation/draft",
        json={"requirement_id": "r1", "requirement_text": "foo", "project_id": str(uuid4())},
    )
    assert g_res.status_code == 200
    g_body = g_res.json()
    assert g_body["generated_text"] == "hello"

    r_res = client.post(
        "/v1/workflow/section/review",
        json={"project_id": str(uuid4()), "section_key": "S-001"},
    )
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "PASS"

    s_res = client.post(
        "/v1/workflow/scoring/calculate",
        json={"project_id": str(uuid4())},
    )
    assert s_res.status_code == 200
    assert s_res.json()["score_total"] == 95.0
