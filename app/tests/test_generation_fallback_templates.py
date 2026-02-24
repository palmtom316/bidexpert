"""Task 3: 章节输出长度与 LLM 全故障兜底 — tests.

Covers:
- R11: section_output_tokens_map provides per-type token limits
- R12/R17: _compose_draft returns structured editable template when all LLMs fail
"""
from __future__ import annotations

import pytest

from app.core.config import settings


# ---------------------------------------------------------------------------
# R11: section_output_tokens_map — per-type token limits
# ---------------------------------------------------------------------------

def test_section_output_tokens_map_exists() -> None:
    """Settings must expose section_output_tokens_map as a dict."""
    token_map = settings.section_output_tokens_map
    assert isinstance(token_map, dict), "section_output_tokens_map must be a dict"


def test_section_output_tokens_map_has_construction_plan() -> None:
    """施工方案 (construction_plan) must have >= 8000 tokens."""
    token_map = settings.section_output_tokens_map
    assert token_map.get("construction_plan", 0) >= 8000


def test_section_output_tokens_map_has_default() -> None:
    """There must be a 'default' key as fallback."""
    token_map = settings.section_output_tokens_map
    assert "default" in token_map
    assert token_map["default"] == settings.section_max_output_tokens


def test_get_section_max_output_tokens_returns_typed_limit() -> None:
    """get_section_max_output_tokens must return type-specific limit."""
    from app.core.config import get_section_max_output_tokens

    assert get_section_max_output_tokens("construction_plan") >= 8000
    assert get_section_max_output_tokens("unknown_type") == settings.section_max_output_tokens


# ---------------------------------------------------------------------------
# R12/R17: fallback template rendering
# ---------------------------------------------------------------------------

def test_compose_fallback_draft_returns_structured_template() -> None:
    """When all LLMs fail, _compose_draft must return a structured,
    human-editable template with section skeleton — not just a snippet."""
    from app.services.fallback_templates import render_fallback_template

    result = render_fallback_template(
        section_type="construction_plan",
        requirement_text="施工组织设计应包含总体施工部署、施工进度计划",
        project_name="某市政道路工程",
        evidence_texts=["我公司具有市政工程一级资质", "项目经理具有一级建造师资格"],
    )
    assert len(result) > 200, "Fallback template must be substantial, not a one-liner"
    assert "施工" in result, "Template must contain domain-relevant content"
    assert "【" in result or "[" in result, "Template must contain placeholder markers"


def test_compose_fallback_draft_without_evidence() -> None:
    """Fallback template must work even with no evidence texts."""
    from app.services.fallback_templates import render_fallback_template

    result = render_fallback_template(
        section_type="construction_plan",
        requirement_text="施工组织设计",
        project_name=None,
        evidence_texts=[],
    )
    assert len(result) > 100
    assert "【" in result or "[" in result


def test_compose_fallback_draft_for_unknown_section_type() -> None:
    """Unknown section types should get a generic but still structured template."""
    from app.services.fallback_templates import render_fallback_template

    result = render_fallback_template(
        section_type="some_unknown_type",
        requirement_text="某项要求",
        project_name="测试项目",
        evidence_texts=[],
    )
    assert len(result) > 50
    assert "【" in result or "[" in result


def test_generation_pipeline_compose_draft_uses_template() -> None:
    """The pipeline's _compose_draft must use template rendering for
    non-trivial fallback instead of snippet concatenation."""
    from app.services.generation_pipeline import _compose_draft

    result = _compose_draft(
        requirement_text="施工组织设计应包含总体施工部署",
        evidence_texts=["我公司具有市政工程一级资质"],
        section_type="construction_plan",
    )
    # Must be longer than old snippet-based approach
    assert len(result) > 100, f"Fallback draft too short ({len(result)} chars)"
