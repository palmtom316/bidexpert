"""Disqualification matrix: structured tracking of disqualification conditions.

Extracts disqualification conditions from tender requirements, checks generated
sections against those conditions, and reports coverage gaps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.extract.tender_parser import ClauseStrength, DISQUALIFY_KEYWORDS


class ConditionCategory(str, Enum):
    QUALIFICATION = "QUALIFICATION"
    TECHNICAL = "TECHNICAL"
    COMMERCIAL = "COMMERCIAL"
    SAFETY = "SAFETY"
    FORMAT = "FORMAT"


_CATEGORY_KEYWORDS: dict[ConditionCategory, list[str]] = {
    ConditionCategory.QUALIFICATION: [
        "资质", "资格", "许可证", "证书", "营业执照", "承装修试",
        "安全生产许可证", "业绩", "人员",
    ],
    ConditionCategory.TECHNICAL: [
        "技术", "方案", "施工组织", "图纸", "参数", "偏离", "偏差",
        "调试方案", "带电作业方案", "设计",
    ],
    ConditionCategory.COMMERCIAL: [
        "报价", "限价", "保证金", "担保", "合同", "商务",
        "围标", "串标", "成本价",
    ],
    ConditionCategory.SAFETY: [
        "安全", "安全方案", "安全生产", "应急", "消防", "高处作业", "带电作业安全",
    ],
    ConditionCategory.FORMAT: [
        "密封", "格式", "签章", "公章", "份数", "逾期", "授权委托",
        "电子签章", "编制",
    ],
}


def _classify_category(text: str) -> ConditionCategory:
    """Classify a disqualification condition into a category."""
    scores: dict[ConditionCategory, int] = {cat: 0 for cat in ConditionCategory}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[cat] += 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else ConditionCategory.FORMAT


@dataclass
class DisqualificationCondition:
    """A single disqualification condition extracted from tender requirements."""
    condition_id: str
    text: str
    strength: ClauseStrength
    category: ConditionCategory
    source_clause: str = ""


@dataclass
class DisqualificationResponse:
    """Result of checking a section against a single condition."""
    condition_id: str
    covered: bool
    evidence_snippet: str = ""


@dataclass
class DisqualificationMatrix:
    """Tracks all disqualification conditions and their coverage status."""
    conditions: list[DisqualificationCondition] = field(default_factory=list)
    responses: list[DisqualificationResponse] = field(default_factory=list)

    def coverage_rate(self) -> float:
        """Return fraction of conditions that have been covered (0.0 - 1.0)."""
        if not self.conditions:
            return 1.0
        covered_ids = {r.condition_id for r in self.responses if r.covered}
        return len(covered_ids) / len(self.conditions)

    def missing_conditions(self) -> list[DisqualificationCondition]:
        """Return conditions that have NOT been covered by any response."""
        covered_ids = {r.condition_id for r in self.responses if r.covered}
        return [c for c in self.conditions if c.condition_id not in covered_ids]

    def disqualify_level_missing(self) -> list[DisqualificationCondition]:
        """Return DISQUALIFY-strength conditions that are not covered."""
        return [
            c for c in self.missing_conditions()
            if c.strength == ClauseStrength.DISQUALIFY
        ]


# Sentence splitting for requirement extraction
_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")


def build_matrix_from_requirements(requirements: list[str]) -> DisqualificationMatrix:
    """Extract disqualification conditions from a list of requirement texts.

    Scans each requirement for DISQUALIFY_KEYWORDS and builds a structured
    matrix of conditions that the bid must address.
    """
    conditions: list[DisqualificationCondition] = []
    seen_texts: set[str] = set()
    cond_idx = 0

    for req_text in requirements:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(req_text) if s.strip()]
        for sentence in sentences:
            matched_keywords = [kw for kw in DISQUALIFY_KEYWORDS if kw in sentence]
            if not matched_keywords:
                continue
            # Deduplicate by normalized text
            norm = sentence.strip()
            if norm in seen_texts:
                continue
            seen_texts.add(norm)

            cond_idx += 1
            # Determine strength: if it contains strong disqualify terms → DISQUALIFY,
            # otherwise REJECT
            strong_terms = {"废标", "否决投标", "取消投标资格", "取消中标资格", "无效投标", "投标无效"}
            strength = (
                ClauseStrength.DISQUALIFY
                if any(t in sentence for t in strong_terms)
                else ClauseStrength.REJECT
            )
            category = _classify_category(sentence)

            conditions.append(DisqualificationCondition(
                condition_id=f"DQ-{cond_idx:03d}",
                text=norm,
                strength=strength,
                category=category,
                source_clause=req_text[:200],
            ))

    return DisqualificationMatrix(conditions=conditions, responses=[])


def check_section_against_matrix(
    section_text: str,
    matrix: DisqualificationMatrix,
) -> DisqualificationMatrix:
    """Check generated section text against the disqualification matrix.

    For each condition, checks if the generated text contains evidence that
    the condition has been addressed. Returns an updated matrix with responses.
    """
    new_responses = list(matrix.responses)

    already_checked = {r.condition_id for r in matrix.responses}

    for condition in matrix.conditions:
        if condition.condition_id in already_checked:
            continue

        # Check if the section text addresses this condition
        # Strategy: look for the key disqualify keywords from the condition
        # appearing in the generated text
        keywords_in_condition = [
            kw for kw in DISQUALIFY_KEYWORDS if kw in condition.text
        ]

        covered = False
        snippet = ""
        for kw in keywords_in_condition:
            if kw in section_text:
                # Find context around the keyword
                idx = section_text.index(kw)
                start = max(0, idx - 30)
                end = min(len(section_text), idx + len(kw) + 30)
                snippet = section_text[start:end]
                covered = True
                break

        # Also check for category-specific addressing
        if not covered:
            cat_keywords = _CATEGORY_KEYWORDS.get(condition.category, [])
            cat_matches = sum(1 for ck in cat_keywords if ck in section_text)
            # If multiple category keywords appear, consider it partially addressed
            if cat_matches >= 2:
                covered = True
                snippet = f"[category match: {condition.category.value}]"

        new_responses.append(DisqualificationResponse(
            condition_id=condition.condition_id,
            covered=covered,
            evidence_snippet=snippet,
        ))

    return DisqualificationMatrix(
        conditions=matrix.conditions,
        responses=new_responses,
    )
