"""Technical requirements extractor — must identify voltage levels (R6)."""

from __future__ import annotations

import logging
import re

from app.extract.tender_parser import ANCHOR_PATTERN, MUST_KEYWORDS
from app.services.tender_analysis import _POWER_ENG_PATTERN
from app.tender.schemas import TechnicalRequirement, TechnicalRequirements

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

_VOLTAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[kK][vV]")
_ENG_TYPE_PATTERN = re.compile(
    r"(变电站|输电线路|配电网|电缆工程|架空线路|新能源|光伏|风电"
    r"|换流站|充电站|储能|微电网|配网自动化)"
)

_TECH_KEYWORDS = [
    "技术要求", "技术标准", "技术规范", "技术参数",
    "施工方案", "施工工艺", "施工方法",
    "质量标准", "验收标准", "试验要求",
    "设备参数", "材料要求", "工器具",
]


def extract_technical(markdown_text: str) -> TechnicalRequirements:
    """Extract technical requirements with deviation tracking and voltage level detection."""
    requirements: list[TechnicalRequirement] = []
    req_idx = 0
    current_anchor: str | None = None

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 10:
            continue

        if ANCHOR_PATTERN.match(line):
            current_anchor = line[:48]

        is_technical = any(k in line for k in _TECH_KEYWORDS)
        is_power = bool(_POWER_ENG_PATTERN.search(line))
        is_must = any(k in line for k in MUST_KEYWORDS)

        if not (is_technical or (is_power and is_must)):
            continue

        voltage_match = _VOLTAGE_PATTERN.search(line)
        eng_match = _ENG_TYPE_PATTERN.search(line)

        # Determine deviation tracking status
        deviation_tracking = "mandatory_response" if is_must else "optional_response"

        req_idx += 1
        requirements.append(TechnicalRequirement(
            req_id=f"TECH-{req_idx:03d}",
            category=_detect_tech_category(line),
            description=line[:500],
            is_mandatory=is_must,
            voltage_level=f"{voltage_match.group(1)}kV" if voltage_match else None,
            engineering_type=eng_match.group(1) if eng_match else None,
            deviation_tracking=deviation_tracking,
            section_anchor=current_anchor,
        ))

    logger.info("extracted %d technical requirements", len(requirements))
    return TechnicalRequirements(requirements=requirements)


def _detect_tech_category(text: str) -> str:
    category_map = {
        "施工": "construction_method",
        "设备": "equipment",
        "材料": "material",
        "试验": "testing",
        "验收": "acceptance",
        "安全": "safety",
        "质量": "quality",
        "工期": "schedule",
        "调试": "commissioning",
        "继电保护": "relay_protection",
        "自动化": "automation",
    }
    for keyword, category in category_map.items():
        if keyword in text:
            return category
    return "general"
