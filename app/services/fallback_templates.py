from __future__ import annotations

from pathlib import Path

from app.core.config import settings

_TEMPLATE_BY_SECTION_TYPE = {
    "施工方案": "section_construction_plan.md",
    "施工组织设计": "section_construction_plan.md",
    "技术方案": "section_technical_plan.md",
    "商务响应": "section_business_response.md",
}
_DEFAULT_TEMPLATE_NAME = "section_default.md"
_MAX_EVIDENCE_ITEMS = 5

_INLINE_DEFAULT_TEMPLATE = """# {{section_type}}（离线兜底草稿）

## 一、对招标要求的响应
{{requirement_text}}

## 二、现有证据摘要
{{evidence_summary}}

## 三、实施与保障措施（待完善）
- 施工组织与资源安排：请结合项目实际补充。
- 质量与安全控制：请补充质量标准、检查频次和责任分工。
- 进度与风险应对：请补充关键里程碑与风险预案。

## 四、需人工补充信息
- 项目特定参数与工期节点
- 关键人员与持证信息
- 与招标条款逐条对应说明
"""


def _fallback_template_dir() -> Path:
    return Path(settings.render_template_dir) / "fallback"


def _template_name(section_type: str | None) -> str:
    normalized = (section_type or "").strip()
    if not normalized:
        return _DEFAULT_TEMPLATE_NAME
    return _TEMPLATE_BY_SECTION_TYPE.get(normalized, _DEFAULT_TEMPLATE_NAME)


def _load_template(section_type: str | None) -> str:
    path = _fallback_template_dir() / _template_name(section_type)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return _INLINE_DEFAULT_TEMPLATE.strip()


def _evidence_summary(evidence_texts: list[str]) -> str:
    bullets: list[str] = []
    for text in evidence_texts:
        snippet = (text or "").strip()
        if not snippet:
            continue
        bullets.append(f"- {snippet[:120]}")
        if len(bullets) >= _MAX_EVIDENCE_ITEMS:
            break
    if not bullets:
        return "- 暂无可用证据，请人工补充依据后再完善正文。"
    return "\n".join(bullets)


def render_section_fallback_template(
    *,
    requirement_text: str,
    evidence_texts: list[str],
    section_type: str | None = None,
) -> str:
    template = _load_template(section_type)
    replacements = {
        "{{section_type}}": (section_type or "通用章节").strip() or "通用章节",
        "{{requirement_text}}": (requirement_text or "").strip() or "请补充本章节招标要求。",
        "{{evidence_summary}}": _evidence_summary(evidence_texts),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered.strip()
