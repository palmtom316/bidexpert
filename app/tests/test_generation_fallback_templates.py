from __future__ import annotations

from types import SimpleNamespace

from app.services.adapters import AdapterUnavailableError, GenerationResult
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
            [RetrievedEvidence(chunk_id="e-1", score=0.9, text="具备同类项目经验。", payload={})],
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


def _mock_profiles(monkeypatch) -> None:
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
        lambda *_: SimpleNamespace(enable_review=False),
    )


def test_section_type_uses_output_token_override(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (GenerationResult(text="LONG_OUTPUT", provider="qwen", model="qwen3.5"), 0),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.estimate_tokens",
        lambda text: 5000 if "LONG_OUTPUT" in text else 100,
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.settings.section_output_tokens_map",
        {"default": 4000, "施工方案": 12000},
        raising=False,
    )

    default_limited = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="请编制技术章节",
        project_id="00000000-0000-0000-0000-000000000010",
    )
    assert default_limited.status == "NEED_HUMAN_INPUT"
    assert "section_token_limit_exceeded" in default_limited.missing_sentences

    typed_ok = generate_draft_with_retrieval(
        requirement_id="REQ-2",
        requirement_text="请编制施工方案章节",
        project_id="00000000-0000-0000-0000-000000000010",
        section_type="施工方案",
    )
    assert typed_ok.status == "SUPPORTED"


def test_generate_returns_editable_template_when_all_providers_fail(monkeypatch) -> None:
    _mock_retrieval(monkeypatch)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (_ for _ in ()).throw(AdapterUnavailableError("all providers unavailable")),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-3",
        requirement_text="请编制施工方案，并说明质量与安全保障措施。",
        project_id="00000000-0000-0000-0000-000000000010",
        section_type="施工方案",
    )

    assert result.status == "SUPPORTED"
    assert "generate_all_providers_failed_local_template" in result.warnings
    assert "## 一、对招标要求的响应" in result.generated_text
    assert "针对要求" not in result.generated_text
