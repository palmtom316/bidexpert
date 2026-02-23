from __future__ import annotations

from app.api.handlers.workflow_generation_review import generate_draft_handler
from app.llm.prompt_suite_v11 import build_review_prompt, build_section_generation_prompt
from app.schemas.contracts import DraftGenerationRequest, DraftGenerationResponse
from app.services.adapters import GenerationResult
from app.services.llm_gateway import generate_with_profile
from app.worker import tasks


def test_section_generation_prompt_includes_typed_constraints() -> None:
    prompt = build_section_generation_prompt(
        global_facts_json={"project_name": "示例项目"},
        relevant_requirements=["需提供施工组织安排"],
        relevant_scoring=[],
        top_chunks=[{"chunk_id": "c-1", "text": "证据"}],
        section_type="施工方案",
    )
    assert "章节类型" in prompt
    assert "施工方案" in prompt
    assert "施工组织" in prompt
    assert "进度计划" in prompt


def test_review_prompt_contains_domain_checklist() -> None:
    prompt = build_review_prompt(
        {"section_path": "3.1", "draft_text": "示例文本"},
        section_type="施工方案",
    )
    assert "工期一致性" in prompt
    assert "证书一致性" in prompt
    assert "参数一致性" in prompt
    assert "废标条款覆盖率" in prompt


def test_generate_draft_handler_forwards_section_type() -> None:
    captured: dict[str, str | None] = {}

    def fake_generate(**kwargs):
        captured["section_type"] = kwargs.get("section_type")
        return DraftGenerationResponse(
            generated_text="ok",
            evidence_ids=["e-1"],
            status="SUPPORTED",
            missing_sentences=[],
            coverage=1.0,
        )

    payload = DraftGenerationRequest(
        requirement_id="REQ-1",
        requirement_text="请编制施工方案",
        section_type="施工方案",
    )
    result = generate_draft_handler(
        payload,
        detect_pricing_content_fn=lambda _text: (False, []),
        generate_draft_with_retrieval_fn=fake_generate,
        service_unavailable_exc_factory=lambda: RuntimeError("should not happen"),
    )

    assert result.status == "SUPPORTED"
    assert captured["section_type"] == "施工方案"


def test_worker_generate_stage_forwards_section_type(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_generate(**kwargs):
        captured["section_type"] = kwargs.get("section_type")
        return DraftGenerationResponse(
            generated_text="ok",
            evidence_ids=["e-1"],
            status="SUPPORTED",
            missing_sentences=[],
            coverage=1.0,
        )

    monkeypatch.setattr(tasks, "generate_draft_with_retrieval", fake_generate)
    result = tasks._generate_stage(
        project_id="00000000-0000-0000-0000-000000000010",
        section_key="S-001",
        requirement_text="请编制施工方案",
        section_type="施工方案",
        industry_tag=None,
        global_facts={},
        retries=0,
    )
    assert result["status"] == "SUPPORTED"
    assert captured["section_type"] == "施工方案"


def test_llm_gateway_passes_section_type_to_adapter_payload(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    class _FakeAdapter:
        def generate(self, payload):  # noqa: ANN001
            captured["section_type"] = payload.section_type
            return GenerationResult(text="ok", provider="fake", model=payload.model)

    monkeypatch.setattr("app.services.llm_gateway._select_adapter", lambda _provider: _FakeAdapter())

    result = generate_with_profile(
        project_id=None,
        provider="fake",
        model="fake-model",
        api_key="k",
        base_url="http://localhost",
        requirement_text="请编制施工方案",
        section_type="施工方案",
        evidence_texts=["证据A"],
        evidence_ids=["e-1"],
        global_facts={},
        relevant_requirements=["r1"],
        relevant_scoring=[],
        top_chunks=[],
    )

    assert result.text == "ok"
    assert captured["section_type"] == "施工方案"
