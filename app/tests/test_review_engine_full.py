from __future__ import annotations

from types import SimpleNamespace

from app.services.review_engine import _build_full_review_report_payload


def test_build_full_review_report_payload_computes_missing_and_coverage() -> None:
    requirements = [
        SimpleNamespace(requirement_code="REQ-1"),
        SimpleNamespace(requirement_code="REQ-2"),
    ]
    sections = [
        SimpleNamespace(section_key="1.1", requirement_codes=["REQ-1"]),
        SimpleNamespace(section_key="1.2", requirement_codes=["REQ-2"]),
    ]
    source = {
        "modeled_issues": [
            {"requirement_code": "REQ-2", "issue_type": "MISSING", "description": "未覆盖 REQ-2"},
            {
                "requirement_code": "REQ-1",
                "issue_type": "LOGICAL_INCONSISTENCY",
                "description": "前后矛盾",
            },
        ],
        "general_comments": "full review done",
    }

    payload = _build_full_review_report_payload(
        status="FAIL",
        source_report=source,
        requirements=requirements,
        sections=sections,
    )

    assert payload["missing_requirements"] == ["REQ-2"]
    assert payload["coverage_estimate"] == 0.5
    assert payload["score_estimate"] == 50.0
    assert payload["logical_inconsistencies"] == ["前后矛盾"]
    assert "未覆盖 REQ-2" in payload["risk_points"]


def test_build_full_review_report_payload_handles_empty_requirements() -> None:
    payload = _build_full_review_report_payload(
        status="WARN",
        source_report={"modeled_issues": []},
        requirements=[],
        sections=[],
    )

    assert payload["coverage_estimate"] == 0.0
    assert payload["score_estimate"] == 0.0
    assert payload["missing_requirements"] == []

