from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError


class ProjectManagerFacts(BaseModel):
    name: str | None = None
    certificate_no: str | None = None


class GlobalFacts(BaseModel):
    project_name: str | None = None
    project_location: str | None = None
    construction_unit: str | None = None
    supervision_unit: str | None = None
    design_unit: str | None = None
    total_duration_days: int | None = Field(default=None, ge=0)
    project_manager: ProjectManagerFacts = Field(default_factory=ProjectManagerFacts)
    voltage_level: str | None = None
    contract_amount: float | None = Field(default=None, ge=0)
    quality_standard: str | None = None
    safety_level: str | None = None
    subcontract_restriction: str | None = None
    milestone_nodes: str | None = None
    bid_bond_amount: float | None = Field(default=None, ge=0)
    performance_bond_ratio: float | None = Field(default=None, ge=0)


_PROJECT_NAME = re.compile(r"(?:项目名称|工程名称)[:：]\s*([^\n\r]+)")
_DURATION = re.compile(r"(?:工期|总工期|计划工期)\s*[:：]?\s*(\d+)\s*天")
_MANAGER = re.compile(r"(?:项目经理|项目负责人)[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,20})")
_CERT = re.compile(r"(?:证书编号|证书号|执业证号)[:：]\s*([A-Za-z0-9\-]{3,40})")
_VOLTAGE = re.compile(r"(\d+(?:\.\d+)?\s*(?:kV|KV|kv))")
_CONTRACT = re.compile(r"(?:合同金额|合同价|中标金额)[:：]?\s*([0-9]+(?:\.[0-9]+)?)")
_LOCATION = re.compile(r"(?:工程地点|项目地点|建设地点)[:：]\s*([^\n\r]+)")
_CONSTRUCTION_UNIT = re.compile(r"(?:建设单位|业主单位|发包人|招标人)[:：]\s*([^\n\r]+)")
_SUPERVISION_UNIT = re.compile(r"(?:监理单位|监理公司)[:：]\s*([^\n\r]+)")
_DESIGN_UNIT = re.compile(r"(?:设计单位|设计院)[:：]\s*([^\n\r]+)")
_QUALITY_STANDARD = re.compile(r"(?:质量标准|质量等级|质量目标|质量要求)[:：]\s*([^\n\r]+)")
_SAFETY_LEVEL = re.compile(r"(?:安全文明等级|安全目标|安全等级)[:：]\s*([^\n\r]+)")
_SUBCONTRACT = re.compile(r"(?:分包限制|分包要求|禁止分包)[:：]\s*([^\n\r]+)")
_MILESTONE = re.compile(r"(?:关键节点|里程碑|工期节点)[:：]\s*([^\n\r]+)")
_BID_BOND = re.compile(r"(?:投标保证金|保证金金额)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:万元|万)?")
_PERF_BOND = re.compile(r"(?:履约保证金|履约担保)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%")


def _extract_with_rules(text: str) -> dict[str, Any]:
    scope = text or ""
    project_name = _PROJECT_NAME.search(scope)
    duration = _DURATION.search(scope)
    manager = _MANAGER.search(scope)
    cert = _CERT.search(scope)
    voltage = _VOLTAGE.search(scope)
    contract = _CONTRACT.search(scope)
    location = _LOCATION.search(scope)
    construction_unit = _CONSTRUCTION_UNIT.search(scope)
    supervision_unit = _SUPERVISION_UNIT.search(scope)
    design_unit = _DESIGN_UNIT.search(scope)
    quality_standard = _QUALITY_STANDARD.search(scope)
    safety_level = _SAFETY_LEVEL.search(scope)
    subcontract = _SUBCONTRACT.search(scope)
    milestone = _MILESTONE.search(scope)
    bid_bond = _BID_BOND.search(scope)
    perf_bond = _PERF_BOND.search(scope)

    facts = {
        "project_name": project_name.group(1).strip() if project_name else None,
        "project_location": location.group(1).strip() if location else None,
        "construction_unit": construction_unit.group(1).strip() if construction_unit else None,
        "supervision_unit": supervision_unit.group(1).strip() if supervision_unit else None,
        "design_unit": design_unit.group(1).strip() if design_unit else None,
        "total_duration_days": int(duration.group(1)) if duration else None,
        "project_manager": {
            "name": manager.group(1).strip() if manager else None,
            "certificate_no": cert.group(1).strip() if cert else None,
        },
        "voltage_level": (voltage.group(1).replace(" ", "") if voltage else None),
        "contract_amount": float(contract.group(1)) if contract else None,
        "quality_standard": quality_standard.group(1).strip() if quality_standard else None,
        "safety_level": safety_level.group(1).strip() if safety_level else None,
        "subcontract_restriction": subcontract.group(1).strip() if subcontract else None,
        "milestone_nodes": milestone.group(1).strip() if milestone else None,
        "bid_bond_amount": float(bid_bond.group(1)) * 10000 if bid_bond else None,
        "performance_bond_ratio": float(perf_bond.group(1)) if perf_bond else None,
    }
    return facts


def _merge_dict(base: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in fallback.items():
        if isinstance(value, dict):
            existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
            merged[key] = _merge_dict(existing, value)
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

    if llm_fallback is not None:
        has_missing = any(
            value is None
            for key, value in rule_facts.items()
            if key != "project_manager"
        ) or any(value is None for value in rule_facts["project_manager"].values())
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

    for field in (
        "project_name", "project_location", "construction_unit", "supervision_unit",
        "design_unit", "total_duration_days", "voltage_level", "contract_amount",
        "quality_standard", "safety_level", "subcontract_restriction",
        "milestone_nodes", "bid_bond_amount", "performance_bond_ratio",
    ):
        base_value = base_facts.get(field)
        candidate_value = candidate_facts.get(field)
        if base_value is None or candidate_value is None:
            continue
        if str(base_value).strip() != str(candidate_value).strip():
            conflicts.append(field)

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
