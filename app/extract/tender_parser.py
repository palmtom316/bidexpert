from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any
from dataclasses import dataclass

from app.core.config import settings
from app.schemas.contracts import ParsedRequirement
from app.services.byok import resolve_profile_chain_for_task

logger = logging.getLogger(__name__)

SENTENCE_SPLIT = re.compile(r"[。；;\n]+")
MUST_KEYWORDS = ["必须", "应当", "不得", "需", "必须满足"]
DISQUALIFY_KEYWORDS = [
    # ── 资质类 ──
    "废标", "否决投标", "不予通过", "取消投标资格", "取消中标资格",
    "拒绝接收", "拒绝投标", "资格审查",
    "资质不符", "资格预审不合格", "无效投标", "投标无效",
    "不具备资格", "资质等级不满足", "证书过期", "许可证失效",
    "未取得安全生产许可证", "无承装修试资质",
    # ── 技术类 ──
    "技术不达标", "技术偏离", "实质性偏离", "重大偏差",
    "不满足技术要求", "技术参数不符", "未响应关键技术条款",
    "未提供施工组织设计", "方案缺失", "图纸缺失",
    "未提交调试方案", "未附带电作业方案",
    # ── 商务类 ──
    "报价超过最高限价", "低于成本价", "围标", "串标",
    "投标保证金不足", "未缴纳投标保证金", "未提供履约担保",
    "未按要求签署合同条款", "商务偏差", "合同条款实质性不响应",
    # ── 安全类 ──
    "未提供安全生产许可证", "安全方案缺失", "未编制专项安全方案",
    "未提供应急预案", "安全等级不满足",
    "缺少带电作业安全措施", "未提供高处作业方案",
    # ── 格式/程序类 ──
    "未按要求密封", "逾期送达", "未按格式要求",
    "未加盖公章", "签章缺失", "授权委托书缺失",
    "投标文件份数不符", "电子签章无效",
    "未按招标文件要求编制",
]
BONUS_PENALTY_KEYWORDS = [
    "加分", "优先考虑", "优先", "扣减", "扣分", "罚款", "处罚",
]
SCORE_PATTERN = re.compile(r"(?:评分|分值|得分)\D{0,5}(\d+(?:\.\d+)?)")
ANCHOR_PATTERN = re.compile(r"^\s*(?:第?[一二三四五六七八九十0-9]+[章节条款、.]|\d+(?:\.\d+)+)")


class ClauseStrength(str, Enum):
    DISQUALIFY = "DISQUALIFY"
    REJECT = "REJECT"
    DEDUCT = "DEDUCT"
    ADVISORY = "ADVISORY"


def classify_clause_strength(text: str) -> ClauseStrength:
    """Classify clause into four strength levels based on keyword matching."""
    if any(k in text for k in (
        "废标", "否决投标", "取消投标资格", "取消中标资格",
        "无效投标", "投标无效", "不予通过", "拒绝投标",
    )):
        return ClauseStrength.DISQUALIFY
    if any(k in text for k in (
        "拒绝", "不予受理", "不予接收", "实质性偏离",
        "重大偏差", "不具备资格", "资质不符",
    )):
        return ClauseStrength.REJECT
    if any(k in text for k in (
        "扣分", "扣减", "罚款", "处罚", "违约金",
        "每延误", "每日罚", "逾期罚",
    )):
        return ClauseStrength.DEDUCT
    return ClauseStrength.ADVISORY


_CROSS_REF = re.compile(
    r"(?:详见|参见|见|按照|依据|根据)\s*"
    r"(?:第?[一二三四五六七八九十\d]+[章节条款]"
    r"|附[录件表]\s*[A-Za-z\d一二三四五六七八九十]*"
    r"|[A-Z]\.\d+(?:\.\d+)*)"
)


def extract_cross_references(text: str) -> list[str]:
    """Extract clause cross-references from text."""
    return [m.group(0).strip() for m in _CROSS_REF.finditer(text)]


_PROMPT_DESCRIPTION = (
    "你是招标规则拆解引擎，专注于电力工程（输变电、配网、新能源）投标文件。"
    "任务：抽取 mandatory_requirements、scoring_items、deliverables。"
    "每条要求必须保留原文片段，不要改写。"
    "尽量补充页码、章节锚点、强制性标记和分值信息。"
    "重点关注：承装修试资质要求、电压等级、带电作业条款、"
    "调试/验收里程碑、电力安全工器具要求、继电保护配置要求。"
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
                    format_constraints={
                        "format_required": "格式" in line,
                        "clause_strength": classify_clause_strength(line).value,
                        "cross_refs": extract_cross_references(line),
                    },
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
