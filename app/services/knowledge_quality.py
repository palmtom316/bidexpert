from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from app.schemas.contracts import EvidenceUpsertItem

_TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_DATE_PATTERN = re.compile(r"(20\d{2}|19\d{2})[./年-](\d{1,2})[./月-](\d{1,2})日?")

_SOURCE_RELIABILITY = {
    "manual_reviewed": 0.95,
    "structured_form": 0.82,
    "enterprise_extract": 0.78,
    "enterprise_table": 0.76,
    "ocr_fallback": 0.68,
    "fallback_block": 0.60,
}

_CATEGORY_HINTS = {
    "COMPANY_QUALIFICATION": ("资质", "证书", "许可", "等级"),
    "COMPANY_PERFORMANCE": ("业绩", "合同", "项目", "金额"),
    "PM_QUALIFICATION_PERFORMANCE": ("项目经理", "建造师", "职称", "业绩"),
    "SAFETY_PRODUCTION": ("安全", "文明施工", "应急", "事故"),
    "QUALITY_MANAGEMENT": ("质量", "检验", "验收", "体系"),
    "EQUIPMENT_CAPABILITY": ("设备", "机械", "型号", "参数"),
    "FINANCIAL_CREDIT": ("财务", "信用", "审计", "负债率"),
    "AWARD_HONORS": ("奖项", "荣誉", "示范", "先进"),
    "SERVICE_COMMITMENT": ("服务", "响应", "承诺", "保障"),
}

_INDUSTRY_HINTS = {
    "电力": ("电力", "变电", "输电", "配电"),
    "政企": ("政府", "政企", "采购", "招标"),
    "建筑": ("施工", "工程", "土建", "结构"),
}


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text or "")]


def infer_valid_to(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    candidates: list[date] = []
    for year_raw, month_raw, day_raw in _DATE_PATTERN.findall(raw):
        try:
            parsed = date(int(year_raw), int(month_raw), int(day_raw))
        except ValueError:
            continue
        candidates.append(parsed)
    if not candidates:
        return None
    return max(candidates).isoformat()


def _resolve_timeliness(valid_to: str | None, *, reference_date: date) -> tuple[float, str]:
    if not valid_to:
        return 0.75, "unknown"
    try:
        end = date.fromisoformat(valid_to)
    except ValueError:
        return 0.70, "unknown"
    days_left = (end - reference_date).days
    if days_left < 0:
        return 0.15, "expired"
    if days_left <= 30:
        return 0.45, "near_expiry"
    if days_left <= 90:
        return 0.65, "valid"
    if days_left <= 365:
        return 0.85, "valid"
    return 1.0, "valid"


def _resolve_completeness(text: str) -> float:
    tokens = _normalize_tokens(text)
    token_count = len(tokens)
    detail_score = _clamp(token_count / 60.0, minimum=0.0, maximum=1.0)
    punctuation_bonus = 0.10 if any(mark in text for mark in ("。", "；", ":", "：", "\n")) else 0.0
    keyword_bonus = 0.10 if any(mark in text for mark in ("必须", "应当", "资质", "业绩", "方案")) else 0.0
    base = 0.30 + detail_score * 0.60 + punctuation_bonus + keyword_bonus
    return _clamp(base, minimum=0.05, maximum=1.0)


def _resolve_relevance(
    *,
    text: str,
    industry_tag: str | None,
    category_key: str | None,
    match_terms: Iterable[str] | None,
) -> float:
    hints: list[str] = []
    normalized_industry = (industry_tag or "").strip()
    if normalized_industry in _INDUSTRY_HINTS:
        hints.extend(_INDUSTRY_HINTS[normalized_industry])
    if category_key and category_key in _CATEGORY_HINTS:
        hints.extend(_CATEGORY_HINTS[category_key])
    if match_terms:
        hints.extend(str(item).strip() for item in match_terms if str(item).strip())

    if not hints:
        return 0.70
    unique_hints = list(dict.fromkeys(hints))
    scope = (text or "").lower()
    matched = sum(1 for token in unique_hints if token.lower() in scope)
    ratio = matched / len(unique_hints)
    return _clamp(0.40 + ratio * 0.60, minimum=0.10, maximum=1.0)


def _resolve_source_reliability(source: str) -> float:
    key = (source or "").strip().lower()
    if key in _SOURCE_RELIABILITY:
        return _SOURCE_RELIABILITY[key]
    return 0.72


@dataclass(frozen=True)
class QualityScore:
    score: float
    timeliness: float
    completeness: float
    relevance: float
    source_reliability: float
    valid_to: str | None
    expiry_status: str


def score_knowledge_quality(
    *,
    text: str,
    source: str,
    industry_tag: str | None = None,
    valid_to: str | None = None,
    confidence: float | None = None,
    category_key: str | None = None,
    match_terms: Iterable[str] | None = None,
    reference_date: date | None = None,
) -> QualityScore:
    today = reference_date or date.today()
    resolved_valid_to = valid_to or infer_valid_to(text)
    timeliness, expiry_status = _resolve_timeliness(resolved_valid_to, reference_date=today)
    completeness = _resolve_completeness(text)
    relevance = _resolve_relevance(
        text=text,
        industry_tag=industry_tag,
        category_key=category_key,
        match_terms=match_terms,
    )
    source_reliability = _resolve_source_reliability(source)

    base_score = (
        timeliness * 0.35
        + completeness * 0.25
        + relevance * 0.20
        + source_reliability * 0.20
    )

    if confidence is not None:
        bounded_confidence = _clamp(float(confidence), minimum=0.0, maximum=1.0)
        base_score *= 0.70 + bounded_confidence * 0.30

    token_count = len(_normalize_tokens(text))
    if expiry_status == "expired":
        base_score -= 0.25
    elif expiry_status == "near_expiry":
        base_score -= 0.08
    if token_count < 12:
        base_score -= 0.08

    final_score = round(_clamp(base_score * 100.0, minimum=0.0, maximum=100.0), 2)
    return QualityScore(
        score=final_score,
        timeliness=round(timeliness, 4),
        completeness=round(completeness, 4),
        relevance=round(relevance, 4),
        source_reliability=round(source_reliability, 4),
        valid_to=resolved_valid_to,
        expiry_status=expiry_status,
    )


def collect_expiry_warnings(
    chunks: list[EvidenceUpsertItem],
    *,
    warning_days: int,
    reference_date: date | None = None,
) -> list[str]:
    today = reference_date or date.today()
    threshold = max(1, int(warning_days))
    warnings: list[str] = []
    for chunk in chunks:
        raw = (chunk.valid_to or "").strip()
        if not raw:
            continue
        try:
            expires_at = date.fromisoformat(raw)
        except ValueError:
            continue
        days_left = (expires_at - today).days
        if days_left < 0:
            warnings.append(f"evidence_expired:{chunk.chunk_id}")
        elif days_left <= threshold:
            warnings.append(f"evidence_near_expiry:{chunk.chunk_id}")
    return warnings


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")
