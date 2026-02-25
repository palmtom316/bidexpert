"""Extract global facts from tender markdown text.

Uses regex-based extraction for deterministic, offline-testable results.
Falls back to LLM extraction when available for fields that regex cannot capture.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Target schema (28 fields + 2 power-specific) ────────────

_EMPTY_FACTS: dict[str, Any] = {
    "project_name": None,
    "project_location": None,
    "construction_unit": None,
    "supervision_unit": None,
    "design_unit": None,
    "total_duration_days": None,
    "project_manager": {"name": None, "certificate_no": None},
    "voltage_level": None,
    "contract_amount": None,
    "quality_standard": None,
    "safety_level": None,
    "subcontract_restriction": None,
    "milestone_nodes": None,
    "bid_bond_amount": None,
    "performance_bond_ratio": None,
    "rated_capacity": None,
    "line_length": None,
    "conductor_type": None,
    "tower_count": None,
    "substation_type": None,
    "commissioning_deadline": None,
    "grid_connection_point": None,
    "seismic_fortification": None,
    "pollution_level": None,
    "altitude": None,
    "design_wind_speed": None,
    "annual_thunder_days": None,
    "owner_project_manager": None,
    "construction_permit_no": None,
    "epc_mode": None,
}

# ── Regex extraction patterns ────────────────────────────────

_EXTRACTORS: list[tuple[str, re.Pattern[str], int | None]] = [
    # (field_name, pattern, group_index_or_None_for_group0)
    ("project_name", re.compile(r"项目名称[：:]\s*(.+?)(?:\n|$)"), 1),
    ("project_location", re.compile(r"(?:项目地点|工程地点|建设地点)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("construction_unit", re.compile(r"(?:建设单位|招标人|业主)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("supervision_unit", re.compile(r"监理单位[：:]\s*(.+?)(?:\n|$)"), 1),
    ("design_unit", re.compile(r"设计单位[：:]\s*(.+?)(?:\n|$)"), 1),
    ("quality_standard", re.compile(r"质量(?:标准|目标|要求)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("safety_level", re.compile(r"安全(?:等级|目标|要求)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("subcontract_restriction", re.compile(r"(?:分包|转包)(?:限制|要求|规定)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("grid_connection_point", re.compile(r"并网点[：:]\s*(.+?)(?:\n|$)"), 1),
    ("owner_project_manager", re.compile(r"业主项目(?:经理|负责人)[：:]\s*(.+?)(?:\n|$)"), 1),
    ("construction_permit_no", re.compile(r"施工许可证[号：:]\s*(.+?)(?:\n|$)"), 1),
    ("conductor_type", re.compile(r"导线(?:型号|规格)[：:为]?\s*(.+?)(?:\n|[，,。])"), 1),
]

_NUMERIC_EXTRACTORS: list[tuple[str, re.Pattern[str], int]] = [
    ("total_duration_days", re.compile(r"(?:合同)?工期[为：:]*\s*(\d+)\s*(?:日历天|天|日)"), 1),
    ("bid_bond_amount", re.compile(r"投标保证金[为：:]*\s*(?:人民币)?\s*(\d+(?:\.\d+)?)\s*万元"), 1),
    ("performance_bond_ratio", re.compile(r"履约保证金[为：:]*\s*(?:合同[金额价]款?的?)?\s*(\d+(?:\.\d+)?)\s*%"), 1),
    ("tower_count", re.compile(r"(?:铁塔|杆塔|塔基)[共计]?\s*(\d+)\s*基"), 1),
    ("altitude", re.compile(r"海拔[约为：:]*\s*(\d+(?:\.\d+)?)\s*(?:m|米)"), 1),
    ("design_wind_speed", re.compile(r"(?:设计)?风速[为：:]*\s*(\d+(?:\.\d+)?)\s*(?:m/s|米/秒)"), 1),
    ("annual_thunder_days", re.compile(r"(?:年均)?雷暴日[数为：:]*\s*(\d+(?:\.\d+)?)\s*(?:天|日|d)"), 1),
]

_VOLTAGE_PATTERN = re.compile(r"(?:电压等级[为：:]*\s*)?(\d+)\s*kV")
_LINE_LENGTH_PATTERN = re.compile(r"(?:线路)?(?:全长|长度)[约为：:]*\s*(\d+(?:\.\d+)?)\s*(?:公里|km|千米)")
_CAPACITY_PATTERN = re.compile(r"(?:主变容量|额定容量|装机容量)[为：:]*\s*(.+?)(?:\n|[，,。])")
_SUBSTATION_PATTERN = re.compile(r"(?:新建|扩建)?(?:户[外内]式|全封闭)?\s*\d*\s*kV\s*(?:变电站|变电所|开关站)")
_COMMISSIONING_PATTERN = re.compile(r"(?:投运|送电|通电)(?:期限|日期|时间|节点)?[为：:]*\s*(.+?)(?:\n|[。])")
_POLLUTION_PATTERN = re.compile(r"污秽等级[为：:]*\s*([a-eA-E]级|[一二三四五]级|[IViv]+级|[轻中重]污区|.{1,10})")
_SEISMIC_PATTERN = re.compile(r"(?:抗震设防[烈度为：:]*\s*(\d+)\s*度|地震加速度[值为：:]*\s*(\d+(?:\.\d+)?)\s*g)")
_EPC_PATTERN = re.compile(r"(EPC|总承包|设计施工一体化|设计采购施工)")
_MILESTONE_PATTERN = re.compile(r"(?:里程碑|关键节点|阶段目标)[：:]\s*(.+?)(?:\n\n|\n(?=[一二三四五六七八九十\d]))")
_CONTRACT_AMOUNT_PATTERN = re.compile(r"(?:合同[金额价]款?|投资[额概]算|工程造价)[为：:]*\s*(?:人民币)?\s*(\d+(?:\.\d+)?)\s*(?:万元|亿元)")


def extract_global_facts(text: str) -> dict[str, Any]:
    """Extract global facts from tender markdown using regex patterns.

    Returns a dict with all 28+ fields. Missing values are None.
    """
    facts = {**_EMPTY_FACTS}

    if not text or not text.strip():
        return facts

    # String extractors
    for field, pattern, group in _EXTRACTORS:
        m = pattern.search(text)
        if m:
            facts[field] = m.group(group).strip()

    # Numeric extractors
    for field, pattern, group in _NUMERIC_EXTRACTORS:
        m = pattern.search(text)
        if m:
            try:
                val = float(m.group(group))
                facts[field] = int(val) if val == int(val) else val
            except (ValueError, TypeError):
                pass

    # Voltage level
    m = _VOLTAGE_PATTERN.search(text)
    if m:
        facts["voltage_level"] = f"{m.group(1)}kV"

    # Line length
    m = _LINE_LENGTH_PATTERN.search(text)
    if m:
        facts["line_length"] = f"{m.group(1)}公里"

    # Rated capacity
    m = _CAPACITY_PATTERN.search(text)
    if m:
        facts["rated_capacity"] = m.group(1).strip()

    # Substation type
    m = _SUBSTATION_PATTERN.search(text)
    if m:
        facts["substation_type"] = m.group(0).strip()

    # Commissioning deadline
    m = _COMMISSIONING_PATTERN.search(text)
    if m:
        facts["commissioning_deadline"] = m.group(1).strip()

    # Pollution level
    m = _POLLUTION_PATTERN.search(text)
    if m:
        facts["pollution_level"] = m.group(1).strip()

    # Seismic fortification
    m = _SEISMIC_PATTERN.search(text)
    if m:
        if m.group(1):
            facts["seismic_fortification"] = f"{m.group(1)}度"
        elif m.group(2):
            facts["seismic_fortification"] = f"{m.group(2)}g"

    # EPC mode
    m = _EPC_PATTERN.search(text)
    if m:
        facts["epc_mode"] = m.group(1).strip()

    # Milestone nodes
    m = _MILESTONE_PATTERN.search(text)
    if m:
        facts["milestone_nodes"] = m.group(1).strip()

    # Contract amount
    m = _CONTRACT_AMOUNT_PATTERN.search(text)
    if m:
        facts["contract_amount"] = f"{m.group(1)}万元" if "万元" in text[m.start():m.end()+5] else f"{m.group(1)}亿元"

    logger.info(
        "global facts extracted: %d/%d fields populated",
        sum(1 for v in facts.values() if v is not None and v != {"name": None, "certificate_no": None}),
        len(facts),
    )
    return facts
