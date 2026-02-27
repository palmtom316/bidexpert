from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.endpoints import redline_v2
from app.schemas.contracts import RedlineCheckRequest, RedlineFinding, RedlineOverrideRequest


def test_redline_returns_blocked_on_p0_negative_deviation() -> None:
    report = redline_v2.run_g2_redline_check(
        RedlineCheckRequest(
            project_id="proj-1",
            tender_package_id="tpkg-1",
            run_active_checks=False,
            parameter_comparisons=[
                {
                    "parameter_name": "主变容量",
                    "required_value": 110.0,
                    "provided_value": 100.0,
                }
            ],
        )
    )

    assert report.status == "BLOCKED"
    assert any(f.severity == "P0" and f.category == "参数偏离" for f in report.findings)


def test_redline_returns_readiness_missing_items() -> None:
    report = redline_v2.run_g2_redline_check(
        RedlineCheckRequest(
            project_id="proj-2",
            tender_package_id="tpkg-2",
            run_active_checks=False,
            findings=[
                RedlineFinding(
                    rule_id="QUAL-001",
                    category="资质",
                    severity="P1",
                    message="缺少110kV同类业绩证明",
                    required_action="缺110kV类似业绩1份",
                )
            ],
            required_documents=["安全生产许可证", "电力资质证书"],
            provided_documents=["安全生产许可证"],
        )
    )

    assert report.status == "NEED_FIX"
    assert "缺110kV类似业绩1份" in report.readiness_missing_items
    assert "缺电力资质证书" in report.readiness_missing_items


def test_redline_override_requires_audit_log(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(redline_v2, "_ctx", lambda: SimpleNamespace(_resolved_created_by=lambda _provided: "jwt-real-user"))
    monkeypatch.setattr(
        "app.services.audit_log.record_audit_event",
        lambda **kwargs: (captured.update(kwargs) or True),
    )

    response = redline_v2.apply_redline_override(
        RedlineOverrideRequest(
            project_id="proj-3",
            tender_package_id="tpkg-3",
            approved_by="spoofed-user",
            override_reason="现场已核验原件并授权放行",
            findings=[
                RedlineFinding(
                    rule_id="PARAM-NEG",
                    category="参数偏离",
                    severity="P0",
                    message="关键参数低于招标要求",
                    required_action="调整配置并补充证明",
                )
            ],
        )
    )

    assert response.status == "OVERRIDDEN"
    assert captured["action"] == "redline.override"
    assert captured["actor_user_id"] == "jwt-real-user"
    assert captured["project_id"] == "proj-3"
    assert captured["target_id"] == "tpkg-3"


def test_redline_override_fails_when_audit_persistence_fails(monkeypatch) -> None:
    monkeypatch.setattr(redline_v2, "_ctx", lambda: SimpleNamespace(_resolved_created_by=lambda _provided: "jwt-real-user"))
    monkeypatch.setattr("app.services.audit_log.record_audit_event", lambda **_kwargs: False)

    with pytest.raises(redline_v2.HTTPException) as exc:
        redline_v2.apply_redline_override(
            RedlineOverrideRequest(
                project_id="proj-4",
                tender_package_id="tpkg-4",
                approved_by="reviewer-2",
                override_reason="需补证后暂时放行",
                findings=[
                    RedlineFinding(
                        rule_id="PARAM-NEG",
                        category="参数偏离",
                        severity="P0",
                        message="关键参数低于招标要求",
                    )
                ],
            )
        )

    assert exc.value.status_code == 503
