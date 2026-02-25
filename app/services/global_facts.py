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
    rated_capacity: str | None = None
    line_length: str | None = None
    conductor_type: str | None = None
    tower_count: int | None = Field(default=None, ge=0)
    substation_type: str | None = None
    commissioning_deadline: str | None = None
    grid_connection_point: str | None = None
    seismic_fortification: str | None = None
    pollution_level: str | None = None
    altitude: str | None = None
    design_wind_speed: str | None = None
    annual_thunder_days: int | None = Field(default=None, ge=0)
    owner_project_manager: str | None = None
    construction_permit_no: str | None = None
    epc_mode: str | None = None


_PROJECT_NAME = re.compile(r"(?:项目名称|工程名称)[:：]\s*([^\n\r]+)")
_DURATION = re.compile(r"(?:工期|总工期|计划工期)\s*[:：]?\s*(\d+)\s*天")
_MANAGER = re.compile(r"(?:项目经理|项目负责人)[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,20})")
_CERT = re.compile(r"(?:证书编号|证书号|执业证号)[:：]\s*([A-Za-z0-9\-]{3,40})")
_VOLTAGE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:kV|KV|kv)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:kV|KV|kv))*"
    r"|±?\d+(?:\.\d+)?\s*(?:kV|KV|kv)"
    r"|\d+(?:\.\d+)?\s*千伏)"
)
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
_RATED_CAPACITY = re.compile(r"(?:额定容量|主变容量|装机容量)[:：]?\s*(\d+(?:\.\d+)?\s*(?:MVA|MW|kVA|kW|万千瓦))")
_LINE_LENGTH = re.compile(r"(?:线路长度|全长|路径长度)[:：]?\s*(\d+(?:\.\d+)?\s*(?:km|公里|千米|m|米))")
_CONDUCTOR_TYPE = re.compile(r"(?:导线型号|导线规格|导线截面|导线类型)[:：]\s*([^\n\r]+)")
_TOWER_COUNT = re.compile(r"(?:杆塔数量|铁塔数量|杆塔总数|基数)[:：]?\s*(\d+)\s*(?:基|座)?")
_SUBSTATION_TYPE = re.compile(r"(?:变电站类型|站型|变电站形式)[:：]\s*([^\n\r]+)")
_COMMISSIONING_DEADLINE = re.compile(r"(?:投运日期|投产日期|送电日期|并网日期)[:：]\s*([^\n\r]+)")
_GRID_CONNECTION = re.compile(r"(?:接入点|并网点|接入系统|接入电网)[:：]\s*([^\n\r]+)")
_SEISMIC = re.compile(r"(?:抗震设防|地震烈度|抗震等级)[:：]?\s*([^\n\r]+)")
_POLLUTION_LEVEL = re.compile(r"(?:污秽等级|污区等级|外绝缘爬距|污染等级)[:：]?\s*([^\n\r]+)")
_ALTITUDE = re.compile(r"(?:海拔高度|海拔|平均海拔)[:：]?\s*(\d+(?:\.\d+)?\s*(?:m|米))")
_DESIGN_WIND = re.compile(r"(?:设计风速|基本风速|最大风速)[:：]?\s*(\d+(?:\.\d+)?\s*(?:m/s|米/秒))")
_THUNDER_DAYS = re.compile(r"(?:雷暴日|年平均雷暴日|雷电日数)[:：]?\s*(\d+)\s*(?:天|日|d)?")
_OWNER_PM = re.compile(r"(?:业主项目经理|甲方项目经理|建设单位项目经理)[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,20})")
_CONSTRUCTION_PERMIT = re.compile(r"(?:施工许可证号|施工许可证编号|建设工程施工许可证)[:：]\s*([A-Za-z0-9\-]+)")
_EPC_MODE = re.compile(r"(?:建设模式|承包模式|工程模式|EPC|总承包)[:：]\s*([^\n\r]+)")


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
    rated_capacity = _RATED_CAPACITY.search(scope)
    line_length = _LINE_LENGTH.search(scope)
    conductor_type = _CONDUCTOR_TYPE.search(scope)
    tower_count = _TOWER_COUNT.search(scope)
    substation_type = _SUBSTATION_TYPE.search(scope)
    commissioning_deadline = _COMMISSIONING_DEADLINE.search(scope)
    grid_connection = _GRID_CONNECTION.search(scope)
    seismic = _SEISMIC.search(scope)
    pollution = _POLLUTION_LEVEL.search(scope)
    altitude_match = _ALTITUDE.search(scope)
    design_wind = _DESIGN_WIND.search(scope)
    thunder_days = _THUNDER_DAYS.search(scope)
    owner_pm = _OWNER_PM.search(scope)
    construction_permit = _CONSTRUCTION_PERMIT.search(scope)
    epc_mode = _EPC_MODE.search(scope)

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
        "rated_capacity": rated_capacity.group(1).strip() if rated_capacity else None,
        "line_length": line_length.group(1).strip() if line_length else None,
        "conductor_type": conductor_type.group(1).strip() if conductor_type else None,
        "tower_count": int(tower_count.group(1)) if tower_count else None,
        "substation_type": substation_type.group(1).strip() if substation_type else None,
        "commissioning_deadline": commissioning_deadline.group(1).strip() if commissioning_deadline else None,
        "grid_connection_point": grid_connection.group(1).strip() if grid_connection else None,
        "seismic_fortification": seismic.group(1).strip() if seismic else None,
        "pollution_level": pollution.group(1).strip() if pollution else None,
        "altitude": altitude_match.group(1).strip() if altitude_match else None,
        "design_wind_speed": design_wind.group(1).strip() if design_wind else None,
        "annual_thunder_days": int(thunder_days.group(1)) if thunder_days else None,
        "owner_project_manager": owner_pm.group(1).strip() if owner_pm else None,
        "construction_permit_no": construction_permit.group(1).strip() if construction_permit else None,
        "epc_mode": epc_mode.group(1).strip() if epc_mode else None,
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
        "rated_capacity", "line_length", "conductor_type", "tower_count",
        "substation_type", "commissioning_deadline", "grid_connection_point",
        "seismic_fortification", "pollution_level", "altitude",
        "design_wind_speed", "annual_thunder_days", "owner_project_manager",
        "construction_permit_no", "epc_mode",
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
