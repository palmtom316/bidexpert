from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError


class ProjectManagerFacts(BaseModel):
    name: str | None = None
    certificate_no: str | None = None


class GlobalFacts(BaseModel):
    project_name: str | None = None
    project_code: str | None = None
    construction_unit: str | None = None
    supervision_unit: str | None = None
    tenderer: str | None = None
    total_duration_days: int | None = Field(default=None, ge=0)
    schedule_milestones: list[str] = Field(default_factory=list)
    quality_standard: str | None = None
    safety_civilization_level: str | None = None
    subcontracting_limit: str | None = None
    bid_bond_amount: float | None = Field(default=None, ge=0)
    performance_bond_amount: float | None = Field(default=None, ge=0)
    warranty_period_months: int | None = Field(default=None, ge=0)
    project_manager: ProjectManagerFacts = Field(default_factory=ProjectManagerFacts)
    voltage_level: str | None = None
    contract_amount: float | None = Field(default=None, ge=0)
    tax_rate: float | None = Field(default=None, ge=0, le=100)


_PROJECT_NAME = re.compile(r"(?:项目名称|工程名称)[:：]\s*([^\n\r]+)")
_PROJECT_CODE = re.compile(r"(?:项目编号|工程编号|招标编号)[:：]\s*([^\s，。；;\n\r]+)")
_CONSTRUCTION_UNIT = re.compile(r"(?:建设单位|业主单位)[:：]\s*([^\n\r，。]+)")
_SUPERVISION_UNIT = re.compile(r"(?:监理单位)[:：]\s*([^\n\r，。]+)")
_TENDERER = re.compile(r"(?:招标人|采购人)[:：]\s*([^\n\r，。]+)")
_DURATION = re.compile(r"(?:工期|总工期|计划工期)\s*[:：]?\s*(\d+)\s*天")
_MILESTONES = re.compile(r"(?:关键节点|工期节点)[:：]\s*([^\n\r]+)")
_QUALITY_STANDARD = re.compile(r"(?:质量标准|质量要求)[:：]\s*([^\n\r；;。]+)")
_SAFETY_LEVEL = re.compile(r"(?:安全文明(?:施工)?等级|安全文明标准)[:：]\s*([^\n\r；;。]+)")
_SUBCONTRACT_LIMIT = re.compile(r"(?:分包限制|分包要求|允许分包范围)[:：]\s*([^\n\r；;。]+)")
_BID_BOND = re.compile(r"(?:投标保证金|保证金)[:：]?\s*([0-9]+(?:\.[0-9]+)?)")
_PERFORMANCE_BOND = re.compile(r"(?:履约保证金)[:：]?\s*([0-9]+(?:\.[0-9]+)?)")
_WARRANTY_MONTHS = re.compile(r"(?:质保期|缺陷责任期)\s*[:：]?\s*(\d+)\s*(?:个月|月)")
_MANAGER = re.compile(r"(?:项目经理|项目负责人)[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,20})")
_CERT = re.compile(r"(?:证书编号|证书号|执业证号)[:：]\s*([A-Za-z0-9\-]{3,40})")
_VOLTAGE = re.compile(r"(\d+(?:\.\d+)?\s*(?:kV|KV|kv))")
_CONTRACT = re.compile(r"(?:合同金额|合同价|中标金额)[:：]?\s*([0-9]+(?:\.[0-9]+)?)")
_TAX_RATE = re.compile(r"(?:税率|增值税率)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%")


def _safe_float(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _parse_milestones(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    parts = re.split(r"[，,；;、]", raw_text)
    return [part.strip() for part in parts if part.strip()]


def _extract_with_rules(text: str) -> dict[str, Any]:
    scope = text or ""
    project_name = _PROJECT_NAME.search(scope)
    project_code = _PROJECT_CODE.search(scope)
    construction_unit = _CONSTRUCTION_UNIT.search(scope)
    supervision_unit = _SUPERVISION_UNIT.search(scope)
    tenderer = _TENDERER.search(scope)
    duration = _DURATION.search(scope)
    milestones = _MILESTONES.search(scope)
    quality_standard = _QUALITY_STANDARD.search(scope)
    safety_level = _SAFETY_LEVEL.search(scope)
    subcontract_limit = _SUBCONTRACT_LIMIT.search(scope)
    bid_bond = _BID_BOND.search(scope)
    performance_bond = _PERFORMANCE_BOND.search(scope)
    warranty_months = _WARRANTY_MONTHS.search(scope)
    manager = _MANAGER.search(scope)
    cert = _CERT.search(scope)
    voltage = _VOLTAGE.search(scope)
    contract = _CONTRACT.search(scope)
    tax_rate = _TAX_RATE.search(scope)

    facts = {
        "project_name": project_name.group(1).strip() if project_name else None,
        "project_code": project_code.group(1).strip() if project_code else None,
        "construction_unit": construction_unit.group(1).strip() if construction_unit else None,
        "supervision_unit": supervision_unit.group(1).strip() if supervision_unit else None,
        "tenderer": tenderer.group(1).strip() if tenderer else None,
        "total_duration_days": int(duration.group(1)) if duration else None,
        "schedule_milestones": _parse_milestones(milestones.group(1) if milestones else None),
        "quality_standard": quality_standard.group(1).strip() if quality_standard else None,
        "safety_civilization_level": safety_level.group(1).strip() if safety_level else None,
        "subcontracting_limit": subcontract_limit.group(1).strip() if subcontract_limit else None,
        "bid_bond_amount": _safe_float(bid_bond),
        "performance_bond_amount": _safe_float(performance_bond),
        "warranty_period_months": int(warranty_months.group(1)) if warranty_months else None,
        "project_manager": {
            "name": manager.group(1).strip() if manager else None,
            "certificate_no": cert.group(1).strip() if cert else None,
        },
        "voltage_level": (voltage.group(1).replace(" ", "") if voltage else None),
        "contract_amount": _safe_float(contract),
        "tax_rate": _safe_float(tax_rate),
    }
    return facts


def _merge_dict(base: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in fallback.items():
        if isinstance(value, dict):
            existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
            merged[key] = _merge_dict(existing, value)
            continue
        if isinstance(value, list):
            existing = merged.get(key)
            if (not isinstance(existing, list) or not existing) and value:
                merged[key] = list(value)
            continue
        if merged.get(key) is None and value is not None:
            merged[key] = value
    return merged


def extract_global_facts_from_text(
    text: str,
    *,
    llm_fallback: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rule_facts = _extract_with_rules(text)

    def _is_missing(key: str, value: Any) -> bool:
        if key == "project_manager":
            return not isinstance(value, dict) or any(item is None for item in value.values())
        if isinstance(value, list):
            return len(value) == 0
        return value is None

    if llm_fallback is not None:
        has_missing = any(_is_missing(key, value) for key, value in rule_facts.items())
        if has_missing:
            llm_facts = llm_fallback(text)
            if isinstance(llm_facts, dict):
                rule_facts = _merge_dict(rule_facts, llm_facts)

    try:
        validated = GlobalFacts.model_validate(rule_facts)
    except ValidationError as exc:
        raise ValueError("global facts schema validation failed") from exc
    return validated.model_dump(mode="json")


def detect_global_fact_conflicts(base_facts: dict[str, Any], candidate_facts: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []

    scalar_fields = (
        "project_name",
        "project_code",
        "construction_unit",
        "supervision_unit",
        "tenderer",
        "total_duration_days",
        "quality_standard",
        "safety_civilization_level",
        "subcontracting_limit",
        "bid_bond_amount",
        "performance_bond_amount",
        "warranty_period_months",
        "voltage_level",
        "contract_amount",
        "tax_rate",
    )
    for field in scalar_fields:
        base_value = base_facts.get(field)
        candidate_value = candidate_facts.get(field)
        if base_value is None or candidate_value is None:
            continue
        if str(base_value).strip() != str(candidate_value).strip():
            conflicts.append(field)

    base_milestones = [str(item).strip() for item in (base_facts.get("schedule_milestones") or []) if str(item).strip()]
    candidate_milestones = [
        str(item).strip() for item in (candidate_facts.get("schedule_milestones") or []) if str(item).strip()
    ]
    if base_milestones and candidate_milestones and base_milestones != candidate_milestones:
        conflicts.append("schedule_milestones")

    base_pm = base_facts.get("project_manager") if isinstance(base_facts.get("project_manager"), dict) else {}
    candidate_pm = (
        candidate_facts.get("project_manager") if isinstance(candidate_facts.get("project_manager"), dict) else {}
    )
    for field in ("name", "certificate_no"):
        base_value = base_pm.get(field)
        candidate_value = candidate_pm.get(field)
        if base_value is None or candidate_value is None:
            continue
        if str(base_value).strip() != str(candidate_value).strip():
            conflicts.append(f"project_manager.{field}")

    return conflicts
