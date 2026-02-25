"""Extract preliminary evaluation items with fatal_if_unmet marking."""

from __future__ import annotations

import logging
import re

from app.extract.tender_parser import (
    DISQUALIFY_KEYWORDS,
    MUST_KEYWORDS,
    SCORE_PATTERN,
    classify_clause_strength,
    extract_cross_references,
    ClauseStrength,
)
from app.tender.schemas import PreliminaryEvaluation, PrelimItem

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

# Additional keywords that indicate preliminary evaluation items
_PRELIM_KEYWORDS = [
    "资格审查", "初审", "形式审查", "资质要求", "投标人资格",
    "投标人须", "投标人应", "投标人必须",
    "营业执照", "安全生产许可证", "承装修试",
    "资质等级", "注册资本", "投标保证金",
]


def extract_preliminary(markdown_text: str) -> PreliminaryEvaluation:
    """Extract preliminary evaluation items from tender markdown.

    Each item is classified by clause strength and marked fatal_if_unmet
    when it could cause bid disqualification.
    """
    items: list[PrelimItem] = []
    item_idx = 0

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 8:
            continue

        # Check if this line is relevant to preliminary evaluation
        is_disqualify = any(k in line for k in DISQUALIFY_KEYWORDS)
        is_must = any(k in line for k in MUST_KEYWORDS)
        is_prelim = any(k in line for k in _PRELIM_KEYWORDS)

        if not (is_disqualify or is_must or is_prelim):
            continue

        strength = classify_clause_strength(line)
        fatal = strength in (ClauseStrength.DISQUALIFY, ClauseStrength.REJECT) or is_disqualify
        cross_refs = extract_cross_references(line)

        item_idx += 1
        items.append(PrelimItem(
            item_id=f"PRE-{item_idx:03d}",
            clause_text=line[:500],
            clause_strength=strength.value,
            fatal_if_unmet=fatal,
            cross_refs=cross_refs,
        ))

    fatal_count = sum(1 for i in items if i.fatal_if_unmet)
    logger.info("extracted %d preliminary items (%d fatal)", len(items), fatal_count)
    return PreliminaryEvaluation(items=items, fatal_count=fatal_count)
