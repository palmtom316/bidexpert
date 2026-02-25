"""Compliance extractor — split preliminary vs detailed evaluation risks."""

from __future__ import annotations

import logging
import re

from app.extract.tender_parser import DISQUALIFY_KEYWORDS, MUST_KEYWORDS, classify_clause_strength, ClauseStrength
from app.tender.schemas import ComplianceCheck, ComplianceItem

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

# Keywords indicating detailed evaluation (not just preliminary)
_DETAILED_KEYWORDS = [
    "评审", "详细评审", "技术评审", "商务评审",
    "综合评分", "打分", "评委", "评标",
]


def extract_compliance(markdown_text: str) -> ComplianceCheck:
    """Extract compliance items, separating preliminary from detailed."""
    preliminary: list[ComplianceItem] = []
    detailed: list[ComplianceItem] = []
    idx = 0

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 8:
            continue

        is_disqualify = any(k in line for k in DISQUALIFY_KEYWORDS)
        is_must = any(k in line for k in MUST_KEYWORDS)
        is_detailed = any(k in line for k in _DETAILED_KEYWORDS)

        if not (is_disqualify or is_must or is_detailed):
            continue

        idx += 1
        strength = classify_clause_strength(line)

        item = ComplianceItem(
            item_id=f"CMP-{idx:03d}",
            clause_text=line[:500],
            check_type="preliminary" if (is_disqualify or strength in (ClauseStrength.DISQUALIFY, ClauseStrength.REJECT)) else "detailed",
            status="PENDING",
            risk_note=strength.value,
        )

        if item.check_type == "preliminary":
            preliminary.append(item)
        else:
            detailed.append(item)

    logger.info("compliance: %d preliminary, %d detailed", len(preliminary), len(detailed))
    return ComplianceCheck(preliminary=preliminary, detailed=detailed)
