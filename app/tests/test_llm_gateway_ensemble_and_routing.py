from __future__ import annotations

from app.services.adapters import AdapterUnavailableError, ComplianceReviewResult, GenerationResult
from app.services.byok.profiles import ResolvedProfile
from app.services import llm_gateway


def test_compliance_review_with_ensemble_uses_majority_vote(monkeypatch) -> None:
    profile_chain = [
        ResolvedProfile("p1", "openai", "gpt-5", "k", "http://x"),
        ResolvedProfile("p2", "deepseek", "deepseek-r1", "k", "http://x"),
        ResolvedProfile("p3", "qwen", "qwen-max", "k", "http://x"),
    ]

    by_model = {
        "gpt-5": ComplianceReviewResult(
            status="PASS",
            report={"status": "PASS", "modeled_issues": [], "coverage_estimate": 0.95},
            provider="openai",
            model="gpt-5",
        ),
        "deepseek-r1": ComplianceReviewResult(
            status="FAIL",
            report={
                "status": "FAIL",
                "modeled_issues": [{"requirement_code": "REQ-1", "issue_type": "MISSING", "description": "遗漏"}],
                "coverage_estimate": 0.55,
            },
            provider="deepseek",
            model="deepseek-r1",
        ),
        "qwen-max": ComplianceReviewResult(
            status="PASS",
            report={"status": "PASS", "modeled_issues": [], "coverage_estimate": 0.88},
            provider="qwen",
            model="qwen-max",
        ),
    }

    monkeypatch.setattr(
        llm_gateway,
        "compliance_review_with_profile",
        lambda **kwargs: by_model[kwargs["model"]],
    )

    result, winner_idx = llm_gateway.compliance_review_with_ensemble(
        profile_chain=profile_chain,
        project_id="proj-1",
        content_text="content",
        requirements=[{"requirement_code": "REQ-1", "strength": "MUST", "original_text": "必须"}],
        ensemble_size=3,
    )

    assert result.status == "PASS"
    assert winner_idx in {0, 2}
    assert "ensemble" in result.report
    assert result.report["ensemble"]["enabled"] is True
    assert result.report["ensemble"]["member_count"] == 3
    assert len(result.report["ensemble"]["votes"]) == 3


def test_generate_fallback_chain_applies_rl_routing_order(monkeypatch) -> None:
    profile_chain = [
        ResolvedProfile("p1", "openai", "gpt-5-mini", "k", "http://x"),
        ResolvedProfile("p2", "deepseek", "deepseek-v3", "k", "http://x"),
    ]
    calls: list[str] = []

    monkeypatch.setattr(llm_gateway, "build_routing_order", lambda **_kwargs: [1, 0])
    monkeypatch.setattr(llm_gateway, "record_route_feedback", lambda **_kwargs: None)

    def fake_generate(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "deepseek-v3":
            return GenerationResult(text="ok", provider=kwargs["provider"], model=kwargs["model"])
        raise AdapterUnavailableError("down")

    monkeypatch.setattr(llm_gateway, "generate_with_profile", fake_generate)

    result, idx = llm_gateway.generate_with_fallback_chain(
        profile_chain=profile_chain,
        project_id="proj-1",
        requirement_text="必须具备类似业绩",
        evidence_texts=["证据1"],
        evidence_ids=["e-1"],
    )

    assert calls[0] == "deepseek-v3"
    assert idx == 1
    assert result.model == "deepseek-v3"
