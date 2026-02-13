from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.contracts import ParsedRequirement

SENTENCE_SPLIT = re.compile(r"[。；;\\n]+")
MUST_KEYWORDS = ["必须", "应当", "不得", "需", "必须满足"]
SCORE_PATTERN = re.compile(r"(?:评分|分值|得分)\\D{0,5}(\\d+(?:\\.\\d+)?)")
ANCHOR_PATTERN = re.compile(r"^\\s*(?:第?[一二三四五六七八九十0-9]+[章节条款、.]|\\d+(?:\\.\\d+)+)")


@dataclass
class ParseResult:
    requirements: list[ParsedRequirement]
    status: str


def _split_pages(text: str) -> list[str]:
    pages = [p.strip() for p in text.split("\\f") if p.strip()]
    return pages if pages else [text]


def parse_tender_requirements(text: str) -> ParseResult:
    pages = _split_pages(text)
    requirements: list[ParsedRequirement] = []

    running_idx = 1
    for page_idx, page in enumerate(pages, start=1):
        current_anchor: str | None = None
        for raw in SENTENCE_SPLIT.split(page):
            line = raw.strip()
            if not line:
                continue

            if ANCHOR_PATTERN.match(line):
                current_anchor = line[:32]

            is_candidate = any(k in line for k in MUST_KEYWORDS) or "评分" in line or "格式" in line
            if not is_candidate:
                continue

            score_match = SCORE_PATTERN.search(line)
            requirements.append(
                ParsedRequirement(
                    requirement_id=f"REQ-{running_idx:04d}",
                    original_text=line,
                    page_no=page_idx,
                    section_anchor=current_anchor,
                    is_must=any(k in line for k in MUST_KEYWORDS),
                    score_weight=float(score_match.group(1)) if score_match else None,
                    format_constraints={"format_required": "格式" in line},
                )
            )
            running_idx += 1

    if not requirements:
        return ParseResult(requirements=[], status="NEED_HUMAN_INPUT")

    return ParseResult(requirements=requirements, status="OK")
