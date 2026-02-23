from __future__ import annotations

from types import SimpleNamespace

from app.core.section_router import is_critical_section, select_generation_plan


def test_keyword_match_marks_section_critical() -> None:
    section = SimpleNamespace(title="第二章 技术方案")
    assert is_critical_section(section) is True


def test_weight_threshold_marks_section_critical() -> None:
    section = SimpleNamespace(title="普通章节", weight=0.9)
    assert is_critical_section(section) is True


def test_select_generation_plan_for_prod_critical() -> None:
    section = SimpleNamespace(title="项目实施方案")
    plan = select_generation_plan(section, env_mode="prod")

    assert plan.is_critical is True
    assert plan.base_model == ("qwen", "qwen-max")
    assert plan.post_enhance_model == ("deepseek", "deepseek-reasoner")
    assert plan.review_model == ("deepseek", "deepseek-reasoner")


def test_select_generation_plan_for_debug_non_critical() -> None:
    section = SimpleNamespace(title="一般说明")
    plan = select_generation_plan(section, env_mode="debug")

    assert plan.is_critical is False
    assert plan.base_model == ("qwen", "qwen-plus")
    assert plan.post_enhance_model is None
    assert plan.review_model == ("deepseek", "deepseek-reasoner")
