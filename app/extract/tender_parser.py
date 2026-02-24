from __future__ import annotations

import logging
import re
from typing import Any
from dataclasses import dataclass

from app.core.config import settings
from app.schemas.contracts import ParsedRequirement
from app.services.byok import resolve_profile_chain_for_task

logger = logging.getLogger(__name__)

SENTENCE_SPLIT = re.compile(r"[。；;\n]+")
MUST_KEYWORDS = ["必须", "应当", "不得", "需", "必须满足"]
DISQUALIFY_KEYWORDS = [
    "废标", "否决投标", "不予通过", "取消投标资格", "取消中标资格",
    "拒绝接收", "拒绝投标", "资格审查",
]
BONUS_PENALTY_KEYWORDS = [
    "加分", "优先考虑", "优先", "扣减", "扣分", "罚款", "处罚",
]
SCORE_PATTERN = re.compile(r"(?:评分|分值|得分)\D{0,5}(\d+(?:\.\d+)?)")
ANCHOR_PATTERN = re.compile(r"^\s*(?:第?[一二三四五六七八九十0-9]+[章节条款、.]|\d+(?:\.\d+)+)")

_PROMPT_DESCRIPTION = (
    "你是招标规则拆解引擎。"
    "任务：抽取 mandatory_requirements、scoring_items、deliverables。"
    "每条要求必须保留原文片段，不要改写。"
    "尽量补充页码、章节锚点、强制性标记和分值信息。"
    "只允许输出结构化结果，不得编造缺失信息。"
)


@dataclass
class ParseResult:
    requirements: list[ParsedRequirement]
    status: str


def _split_pages(text: str) -> list[str]:
    pages = [p.strip() for p in text.split("\f") if p.strip()]
    return pages if pages else [text]


def _field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _run_langextract(*, text: str, model_id: str) -> list[Any]:
    import langextract as lx

    example = lx.data.ExampleData(
        text="投标人必须具备ISO9001资质，技术评分分值10分，格式须符合招标文件模板。",
        extractions=[
            lx.data.Extraction(
                extraction_class="合规要求",
                extraction_text="投标人必须具备ISO9001资质",
                attributes={"is_must": True, "section_anchor": "第一章 资格条件"},
            ),
            lx.data.Extraction(
                extraction_class="评分项",
                extraction_text="技术评分分值10分",
                attributes={"score_weight": 10.0, "section_anchor": "第三章 评分办法"},
            ),
            lx.data.Extraction(
                extraction_class="格式要求",
                extraction_text="格式须符合招标文件模板",
                attributes={"format_required": True},
            ),
        ],
    )
    result = lx.extract(
        text_or_documents=text,
        prompt_description=_PROMPT_DESCRIPTION,
        examples=[example],
        model_id=model_id,
    )
    return list(getattr(result, "extractions", []))


def _model_candidates() -> list[str]:
    candidates: list[str] = []
    for profile in resolve_profile_chain_for_task(project_id=None, task_type="EXTRACT"):
        model = (profile.model or "").strip()
        if model and model not in candidates:
            candidates.append(model)

    default_model = (settings.langextract_default_model or "").strip()
    if default_model and default_model not in candidates:
        candidates.append(default_model)
    return candidates


def _parse_with_llm(text: str) -> list[ParsedRequirement]:
    candidates = _model_candidates()
    if not candidates:
        return []

    raw_extractions: list[Any] = []
    for model_id in candidates:
        try:
            raw_extractions = _run_langextract(text=text, model_id=model_id)
            if raw_extractions:
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning("langextract failed for model=%s: %s", model_id, exc)
            continue

    requirements: list[ParsedRequirement] = []
    for idx, item in enumerate(raw_extractions, start=1):
        line = str(_field(item, "extraction_text", "")).strip()
        if not line:
            continue

        attrs = _field(item, "attributes", {}) or {}
        attrs_dict = attrs if isinstance(attrs, dict) else {}
        score_weight = _safe_float(attrs_dict.get("score_weight"))
        if score_weight is None:
            score_match = SCORE_PATTERN.search(line)
            if score_match:
                score_weight = _safe_float(score_match.group(1))

        is_must_attr = attrs_dict.get("is_must")
        if isinstance(is_must_attr, bool):
            is_must = is_must_attr
        else:
            is_must = any(k in line for k in MUST_KEYWORDS)

        section_anchor_raw = attrs_dict.get("section_anchor")
        section_anchor = str(section_anchor_raw).strip() if section_anchor_raw else None
        page_no = _safe_int(attrs_dict.get("page_no"))
        format_required = bool(attrs_dict.get("format_required")) or ("格式" in line)

        requirements.append(
            ParsedRequirement(
                requirement_id=f"REQ-{idx:04d}",
                original_text=line,
                page_no=page_no,
                section_anchor=section_anchor,
                is_must=is_must,
                score_weight=score_weight,
                format_constraints={"format_required": format_required},
            )
        )
    return requirements


def _parse_with_regex(text: str) -> list[ParsedRequirement]:
    pages = _split_pages(text)
    requirements: list[ParsedRequirement] = []

    running_idx = 1
    for page_idx, page in enumerate(pages, start=1):
        current_anchor: str | None = None
        for raw in SENTENCE_SPLIT.split(page):
            line = raw.strip()
            if not line:
                continue

            if ANCHOR_PATTERN.match(line):
                current_anchor = line[:32]

            is_candidate = (
                any(k in line for k in MUST_KEYWORDS)
                or any(k in line for k in DISQUALIFY_KEYWORDS)
                or any(k in line for k in BONUS_PENALTY_KEYWORDS)
                or "评分" in line
                or "格式" in line
            )
            if not is_candidate:
                continue

            score_match = SCORE_PATTERN.search(line)
            requirements.append(
                ParsedRequirement(
                    requirement_id=f"REQ-{running_idx:04d}",
                    original_text=line,
                    page_no=page_idx,
                    section_anchor=current_anchor,
                    is_must=(
                        any(k in line for k in MUST_KEYWORDS)
                        or any(k in line for k in DISQUALIFY_KEYWORDS)
                    ),
                    score_weight=float(score_match.group(1)) if score_match else None,
                    format_constraints={"format_required": "格式" in line},
                )
            )
            running_idx += 1

    return requirements


def parse_tender_requirements(text: str) -> ParseResult:
    llm_requirements = _parse_with_llm(text)
    if llm_requirements:
        return ParseResult(requirements=llm_requirements, status="OK")

    requirements = _parse_with_regex(text)
    if not requirements:
        return ParseResult(requirements=[], status="NEED_HUMAN_INPUT")

    return ParseResult(requirements=requirements, status="OK")
