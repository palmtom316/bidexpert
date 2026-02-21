from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError


class ProjectManagerFacts(BaseModel):
    name: str | None = None
    certificate_no: str | None = None


class GlobalFacts(BaseModel):
    project_name: str | None = None
    total_duration_days: int | None = Field(default=None, ge=0)
    project_manager: ProjectManagerFacts = Field(default_factory=ProjectManagerFacts)
    voltage_level: str | None = None
    contract_amount: float | None = Field(default=None, ge=0)


_PROJECT_NAME = re.compile(r"(?:项目名称|工程名称)[:：]\s*([^\n\r]+)")
_DURATION = re.compile(r"(?:工期|总工期|计划工期)\s*[:：]?\s*(\d+)\s*天")
_MANAGER = re.compile(r"(?:项目经理|项目负责人)[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,20})")
_CERT = re.compile(r"(?:证书编号|证书号|执业证号)[:：]\s*([A-Za-z0-9\-]{3,40})")
_VOLTAGE = re.compile(r"(\d+(?:\.\d+)?\s*(?:kV|KV|kv))")
_CONTRACT = re.compile(r"(?:合同金额|合同价|中标金额)[:：]?\s*([0-9]+(?:\.[0-9]+)?)")


def _extract_with_rules(text: str) -> dict[str, Any]:
    scope = text or ""
    project_name = _PROJECT_NAME.search(scope)
    duration = _DURATION.search(scope)
    manager = _MANAGER.search(scope)
    cert = _CERT.search(scope)
    voltage = _VOLTAGE.search(scope)
    contract = _CONTRACT.search(scope)

    facts = {
        "project_name": project_name.group(1).strip() if project_name else None,
        "total_duration_days": int(duration.group(1)) if duration else None,
        "project_manager": {
            "name": manager.group(1).strip() if manager else None,
            "certificate_no": cert.group(1).strip() if cert else None,
        },
        "voltage_level": (voltage.group(1).replace(" ", "") if voltage else None),
        "contract_amount": float(contract.group(1)) if contract else None,
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

    for field in ("project_name", "total_duration_days", "voltage_level", "contract_amount"):
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
