from __future__ import annotations

from types import SimpleNamespace

from app.core.section_router import SectionGenerationPlan
from app.services.adapters import GenerationResult, ReviewResult
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
    gen_primary = ResolvedProfile("00000000-0000-0000-0000-000000000002", "qwen", "qwen-max", "k", "http://x")
    review_primary = ResolvedProfile(
        "00000000-0000-0000-0000-000000000001",
        "deepseek",
        "deepseek-reasoner",
        "k",
        "http://x",
    )

    def _resolve_profile(*, project_id, task_type):  # noqa: ANN001
        del project_id
        return review_primary if task_type == "REVIEW" else gen_primary

    def _resolve_chain(*, project_id, task_type):  # noqa: ANN001
        del project_id
        if task_type == "REVIEW":
            return [review_primary]
        return [gen_primary]

    monkeypatch.setattr("app.services.generation_pipeline.resolve_profile_for_task", _resolve_profile)
    monkeypatch.setattr("app.services.generation_pipeline.resolve_profile_chain_for_task", _resolve_chain)



def test_critical_section_forces_review_and_uses_enhance(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.get_project_model_policy",
        lambda _: SimpleNamespace(enable_review=False),
    )
    monkeypatch.setattr("app.services.generation_pipeline.current_registry_mode", lambda: "prod")
    monkeypatch.setattr(
        "app.services.generation_pipeline.select_generation_plan",
        lambda *_args, **_kwargs: SectionGenerationPlan(
            is_critical=True,
            base_model=("qwen", "qwen-max"),
            post_enhance_model=("deepseek", "deepseek-reasoner"),
            review_model=("deepseek", "deepseek-reasoner"),
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (GenerationResult(text="这是生成草稿内容。", provider="qwen", model="qwen-max"), 0),
    )

    calls = {"enhance": 0, "review": 0}

    def _enhance(**kwargs):  # noqa: ANN003
        calls["enhance"] += 1
        return SimpleNamespace(
            text="这是增强后的草稿内容。",
            payload={"fixed_md": "这是增强后的草稿内容。", "issues": [], "pass": True, "suggestions": []},
            provider="deepseek",
            model="deepseek-reasoner",
            fallback_index=0,
            warnings=["enhance_applied"],
        )

    def _review(**kwargs):  # noqa: ANN003
        calls["review"] += 1
        return ReviewResult(approved=True, issues=[], provider="deepseek", model="deepseek-reasoner"), 0

    monkeypatch.setattr("app.services.generation_pipeline._run_section_enhance_step", _enhance)
    monkeypatch.setattr("app.services.generation_pipeline.review_with_fallback_chain", _review)

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须具备类似项目经验",
        project_id="00000000-0000-0000-0000-000000000010",
        section_context={"section_title": "技术方案"},
    )

    assert calls["enhance"] == 1
    assert calls["review"] == 1
    assert result.generated_text == "这是增强后的草稿内容。"
    assert any(item.startswith("section_route:") for item in result.warnings)


def test_section_type_output_limit_allows_long_construction_plan(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.get_project_model_policy",
        lambda _: SimpleNamespace(enable_review=False),
    )
    monkeypatch.setattr("app.services.generation_pipeline.current_registry_mode", lambda: "prod")
    monkeypatch.setattr(
        "app.services.generation_pipeline.select_generation_plan",
        lambda *_args, **_kwargs: SectionGenerationPlan(
            is_critical=False,
            base_model=("qwen", "qwen-max"),
            post_enhance_model=None,
            review_model=("deepseek", "deepseek-reasoner"),
        ),
    )
    long_text = "施工方案" * 2500
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (GenerationResult(text=long_text, provider="qwen", model="qwen-max"), 0),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline._run_section_enhance_step",
        lambda **_: SimpleNamespace(
            text=long_text,
            payload={"fixed_md": long_text, "issues": [], "pass": True, "suggestions": []},
            provider="qwen",
            model="qwen-max",
            fallback_index=0,
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.estimate_tokens",
        lambda text: 5000 if text == long_text else 100,
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-2",
        requirement_text="请提供完整施工组织设计",
        project_id="00000000-0000-0000-0000-000000000010",
        section_context={"section_title": "施工组织设计", "section_type": "construction_plan"},
    )

    assert result.status != "NEED_HUMAN_INPUT"
