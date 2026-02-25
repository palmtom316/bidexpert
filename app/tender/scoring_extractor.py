"""Scoring model extractor — reuses SCORE_PATTERN from tender_parser."""

from __future__ import annotations

import logging
import re

from app.extract.tender_parser import ANCHOR_PATTERN, SCORE_PATTERN
from app.tender.schemas import ScoringItem, ScoringModel

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

# Scoring category patterns
_SCORING_SECTION_KEYWORDS = [
    "评分", "评审", "评标", "打分", "分值", "得分",
    "技术评分", "商务评分", "价格评分", "综合评分",
]

_CATEGORY_MAP = {
    "技术": "technical",
    "商务": "commercial",
    "价格": "pricing",
    "报价": "pricing",
    "综合": "comprehensive",
    "资信": "qualification",
    "业绩": "performance",
    "方案": "proposal",
    "施工": "construction",
    "安全": "safety",
    "质量": "quality",
    "工期": "schedule",
    "进度": "schedule",
}


def extract_scoring(markdown_text: str) -> ScoringModel:
    """Extract scoring model items from tender text."""
    items: list[ScoringItem] = []
    total_score = 100.0
    item_idx = 0
    current_anchor: str | None = None

    # Try to detect total score
    total_match = re.search(r"满分\D{0,5}(\d+(?:\.\d+)?)\s*分", markdown_text)
    if total_match:
        try:
            total_score = float(total_match.group(1))
        except ValueError:
            pass

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 6:
            continue

        if ANCHOR_PATTERN.match(line):
            current_anchor = line[:48]

        # Only process lines with scoring keywords
        if not any(k in line for k in _SCORING_SECTION_KEYWORDS):
            continue

        score_match = SCORE_PATTERN.search(line)
        if not score_match:
            continue

        max_score = float(score_match.group(1))
        category = _detect_category(line)

        item_idx += 1
        items.append(ScoringItem(
            item_id=f"SCR-{item_idx:03d}",
            category=category,
            description=line[:300],
            max_score=max_score,
            weight=max_score / total_score if total_score > 0 else None,
            section_anchor=current_anchor,
        ))

    logger.info("extracted %d scoring items, total=%.1f", len(items), total_score)
    return ScoringModel(total_score=total_score, items=items)


def _detect_category(text: str) -> str:
    for keyword, category in _CATEGORY_MAP.items():
        if keyword in text:
            return category
    return "other"
