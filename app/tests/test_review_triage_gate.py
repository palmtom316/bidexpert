from __future__ import annotations

from types import SimpleNamespace

from app.services.adapters import GenerationResult, ReviewResult
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.qdrant_store import RetrievedEvidence
from app.services.review_engine import resolve_triage_gate


def test_triage_gate_pass_when_review_passes_and_disqualify_covered() -> None:
    gate = resolve_triage_gate(
        review_status="PASS",
        review_report={"issues": [], "disqualify_clause_coverage": True},
        warnings=[],
        disqualify_coverage_ok=True,
    )
    assert gate == "PASS"


def test_triage_gate_adjust_pass_when_warnings_present() -> None:
    gate = resolve_triage_gate(
        review_status="PASS",
        review_report={"issues": [], "disqualify_clause_coverage": True},
        warnings=["global_facts_conflict:project_name"],
        disqualify_coverage_ok=True,
    )
    assert gate == "ADJUST_PASS"


def test_triage_gate_rewrite_when_disqualify_clause_not_covered() -> None:
    gate = resolve_triage_gate(
        review_status="PASS",
        review_report={"issues": [], "disqualify_clause_coverage": False},
        warnings=[],
        disqualify_coverage_ok=False,
    )
    assert gate == "REWRITE"


def test_generation_pipeline_sets_adjust_pass_to_need_human_input(monkeypatch) -> None:
    monkeypatch.setattr("app.services.generation_pipeline.decompose_requirement", lambda _: ["sub-1"])
    monkeypatch.setattr(
        "app.services.generation_pipeline.retrieve_for_subrequirements",
        lambda **_: {"sub-1": []},
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.merge_retrieval",
        lambda _: (
            ["e-1"],
            {"sub-1": ["e-1"]},
            [RetrievedEvidence(chunk_id="e-1", score=0.9, text="具备类似经验。", payload={})],
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.run_three_gates",
        lambda **_: SimpleNamespace(status="SUPPORTED", missing_sentences=[], coverage=1.0),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.reserve_budget_persistent",
        lambda **_: (True, 1000),
    )
    monkeypatch.setattr("app.services.generation_pipeline.log_llm_call", lambda **_: None)
    monkeypatch.setattr("app.services.generation_pipeline.get_cache", lambda *_: None)
    monkeypatch.setattr("app.services.generation_pipeline.set_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.services.generation_pipeline._global_fact_conflict_warnings",
        lambda *_args, **_kwargs: ["global_facts_conflict:project_name"],
    )

    profile = SimpleNamespace(
        profile_id="00000000-0000-0000-0000-000000000001",
        provider="qwen",
        model="qwen3.5",
        api_key=None,
        base_url=None,
    )
    monkeypatch.setattr("app.services.generation_pipeline.resolve_profile_for_task", lambda **_: profile)
    monkeypatch.setattr("app.services.generation_pipeline.resolve_profile_chain_for_task", lambda **_: [profile])
    monkeypatch.setattr(
        "app.services.generation_pipeline.get_project_model_policy",
        lambda *_: SimpleNamespace(enable_review=True),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (GenerationResult(text="生成草稿内容。", provider="qwen", model="qwen3.5"), 0),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.review_with_fallback_chain",
        lambda **_: (
            ReviewResult(
                approved=True,
                issues=[],
                provider="qwen",
                model="qwen3.5",
                report={"status": "PASS", "disqualify_clause_coverage": True},
            ),
            0,
        ),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须满足资格条件。",
        project_id="00000000-0000-0000-0000-000000000010",
    )

    assert result.review_gate == "ADJUST_PASS"
    assert result.status == "NEED_HUMAN_INPUT"
