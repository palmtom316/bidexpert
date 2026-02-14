from __future__ import annotations

from types import SimpleNamespace

from app.services.adapters import AdapterUnavailableError, GenerationResult, ReviewResult
from app.services.byok.profiles import ResolvedProfile
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.qdrant_store import RetrievedEvidence


def _mock_retrieval(monkeypatch) -> None:
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


def _mock_profiles(monkeypatch) -> None:
    def _resolver(*, project_id, task_type):  # noqa: ANN001
        if task_type == "REVIEW":
            return ResolvedProfile("00000000-0000-0000-0000-000000000001", "openai", "gpt-review", "k", "http://x")
        return ResolvedProfile("00000000-0000-0000-0000-000000000002", "qwen", "qwen-gen", "k", "http://x")

    monkeypatch.setattr("app.services.generation_pipeline.resolve_profile_for_task", _resolver)
    monkeypatch.setattr(
        "app.services.generation_pipeline.get_project_model_policy",
        lambda _: SimpleNamespace(enable_review=True),
    )


def test_review_fallback_to_local_validator(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_profile",
        lambda **_: GenerationResult(text="这是生成草稿内容，覆盖需求。", provider="qwen", model="qwen-gen"),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.review_with_profile",
        lambda **_: (_ for _ in ()).throw(AdapterUnavailableError("down")),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须具备类似项目经验",
        project_id="00000000-0000-0000-0000-000000000010",
    )

    assert "review_fallback_local_validator" in result.warnings


def test_review_reject_sets_need_human_input(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_profile",
        lambda **_: GenerationResult(text="这是生成草稿内容，覆盖需求。", provider="qwen", model="qwen-gen"),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.review_with_profile",
        lambda **_: ReviewResult(
            approved=False,
            issues=["insufficient_evidence"],
            provider="openai",
            model="gpt-review",
        ),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须具备类似项目经验",
        project_id="00000000-0000-0000-0000-000000000010",
    )

    assert result.status == "NEED_HUMAN_INPUT"
    assert "review_issue:insufficient_evidence" in result.warnings


def test_review_fallback_provider_used(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_profile",
        lambda **_: GenerationResult(text="这是生成草稿内容，覆盖需求。", provider="qwen", model="qwen-gen"),
    )

    calls = {"count": 0}

    def _review(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise AdapterUnavailableError("down")
        return ReviewResult(approved=True, issues=[], provider="deepseek", model="ds-review")

    monkeypatch.setattr("app.services.generation_pipeline.review_with_profile", _review)
    monkeypatch.setattr("app.services.generation_pipeline.settings.review_fallback_provider", "deepseek")
    monkeypatch.setattr("app.services.generation_pipeline.settings.review_fallback_model", "ds-review")
    monkeypatch.setattr("app.services.generation_pipeline.settings.review_fallback_base_url", "http://x")
    monkeypatch.setattr("app.services.generation_pipeline.settings.review_fallback_api_key", "k")

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须具备类似项目经验",
        project_id="00000000-0000-0000-0000-000000000010",
    )

    assert "review_fallback_provider_used" in result.warnings
