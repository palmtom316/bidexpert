"""Task 6: 章节类型化生成与审查清单 — tests.

Covers:
- R09: build_section_generation_prompt accepts section_type and includes
       type-specific structural constraints and terminology.
- R10: build_review_prompt accepts section_type and includes domain
       review checklist (consistency, parameters, disqualification coverage).
"""
from __future__ import annotations

from app.llm.prompt_suite_v11 import (
    build_section_generation_prompt,
    build_review_prompt,
)

_COMMON_KWARGS = dict(
    global_facts_json={"project_name": "test"},
    relevant_requirements=["req1"],
    relevant_scoring=["score1"],
    top_chunks=[{"chunk_id": "c1"}],
)


# ---------------------------------------------------------------------------
# R09: section-typed generation prompt
# ---------------------------------------------------------------------------

def test_generation_prompt_accepts_section_type() -> None:
    """build_section_generation_prompt must accept section_type kwarg."""
    prompt = build_section_generation_prompt(section_type="construction_plan", **_COMMON_KWARGS)
    assert isinstance(prompt, str) and len(prompt) > 0


def test_construction_plan_prompt_has_schedule_guidance() -> None:
    prompt = build_section_generation_prompt(section_type="construction_plan", **_COMMON_KWARGS)
    assert "施工" in prompt or "进度" in prompt or "工期" in prompt


def test_safety_plan_prompt_has_safety_guidance() -> None:
    prompt = build_section_generation_prompt(section_type="safety_plan", **_COMMON_KWARGS)
    assert "安全" in prompt


def test_quality_plan_prompt_has_quality_guidance() -> None:
    prompt = build_section_generation_prompt(section_type="quality_plan", **_COMMON_KWARGS)
    assert "质量" in prompt


def test_technical_proposal_prompt_has_technical_guidance() -> None:
    prompt = build_section_generation_prompt(section_type="technical_proposal", **_COMMON_KWARGS)
    assert "技术" in prompt


def test_different_section_types_produce_different_prompts() -> None:
    p1 = build_section_generation_prompt(section_type="construction_plan", **_COMMON_KWARGS)
    p2 = build_section_generation_prompt(section_type="safety_plan", **_COMMON_KWARGS)
    assert p1 != p2, "Different section types must produce different prompts"


def test_unknown_section_type_still_works() -> None:
    prompt = build_section_generation_prompt(section_type="unknown_type", **_COMMON_KWARGS)
    assert isinstance(prompt, str) and len(prompt) > 0


# ---------------------------------------------------------------------------
# R10: domain review checklist
# ---------------------------------------------------------------------------

def test_review_prompt_accepts_section_type() -> None:
    """build_review_prompt must accept section_type kwarg."""
    prompt = build_review_prompt({"content": "test"}, section_type="construction_plan")
    assert isinstance(prompt, str) and len(prompt) > 0


def test_review_prompt_has_consistency_check() -> None:
    prompt = build_review_prompt({"content": "test"}, section_type="construction_plan")
    assert "一致性" in prompt or "consistency" in prompt.lower() or "工期" in prompt


def test_review_prompt_has_disqualification_coverage() -> None:
    prompt = build_review_prompt({"content": "test"}, section_type="construction_plan")
    assert "废标" in prompt or "否决" in prompt or "disqualif" in prompt.lower()


def test_review_prompt_has_parameter_check() -> None:
    prompt = build_review_prompt({"content": "test"}, section_type="technical_proposal")
    assert "参数" in prompt or "技术" in prompt


def test_review_prompt_safety_has_safety_checklist() -> None:
    prompt = build_review_prompt({"content": "test"}, section_type="safety_plan")
    assert "安全" in prompt
