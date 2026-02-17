from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.api import routes
from app.schemas.contracts import ReviewFullRequest


def test_review_full_api_route(monkeypatch) -> None:
    report = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        section_key="__FULL__",
        status="PASS",
        report_json={"coverage_estimate": 1.0},
        created_at=datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(routes, "run_full_compliance_review", lambda *_args, **_kwargs: report)

    resp = routes.review_full_api(
        ReviewFullRequest(project_id="22222222-2222-2222-2222-222222222222", outline_id="outline-1")
    )

    assert resp.section_key == "__FULL__"
    assert resp.status == "PASS"
    assert resp.report_json["coverage_estimate"] == 1.0


def test_review_full_api_route_passes_ensemble_options(monkeypatch) -> None:
    report = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        section_key="__FULL__",
        status="PASS",
        report_json={"coverage_estimate": 1.0},
        created_at=datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    )
    captured: dict[str, object] = {}

    def fake_run(project_id: str, outline_id: str | None, **kwargs):
        captured["project_id"] = project_id
        captured["outline_id"] = outline_id
        captured.update(kwargs)
        return report

    monkeypatch.setattr(routes, "run_full_compliance_review", fake_run)

    resp = routes.review_full_api(
        ReviewFullRequest(
            project_id="22222222-2222-2222-2222-222222222222",
            outline_id="outline-1",
            enable_ensemble=True,
            ensemble_size=2,
        )
    )

    assert resp.status == "PASS"
    assert captured["enable_ensemble"] is True
    assert captured["ensemble_size"] == 2
