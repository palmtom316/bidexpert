"""Split full.md into logical sections based on Chinese heading anchors."""

from __future__ import annotations

import logging
import re

from app.extract.tender_parser import ANCHOR_PATTERN
from app.tender.schemas import TenderSection, TenderSections

logger = logging.getLogger(__name__)

# Extended anchor for top-level chapter headings (第一章, 第二章, etc.)
_CHAPTER_PATTERN = re.compile(
    r"^#{1,4}\s+(?:第?[一二三四五六七八九十\d]+[章部篇])"
    r"|^(?:第?[一二三四五六七八九十\d]+[章部篇])",
)

# Markdown heading pattern
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def sectionize(markdown_text: str) -> TenderSections:
    """Split markdown text into sections by heading anchors.

    Strategy:
    1. Split by lines
    2. Detect section boundaries via ANCHOR_PATTERN and markdown headings
    3. Accumulate content between boundaries into TenderSection objects
    """
    lines = markdown_text.splitlines()
    sections: list[TenderSection] = []
    current_anchor: str | None = None
    current_title: str = ""
    current_lines: list[str] = []
    section_idx = 0

    def _flush():
        nonlocal section_idx
        if current_lines and current_anchor:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(
                    TenderSection(
                        section_id=f"S-{section_idx:03d}",
                        anchor=current_anchor,
                        title=current_title or current_anchor,
                        content=content,
                    )
                )
                section_idx += 1

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append(line)
            continue

        # Check markdown heading
        md_match = _MD_HEADING.match(stripped)
        is_anchor = bool(ANCHOR_PATTERN.match(stripped)) or bool(_CHAPTER_PATTERN.match(stripped))

        if md_match and is_anchor:
            _flush()
            current_anchor = stripped[:64]
            current_title = md_match.group(2).strip()[:64]
            current_lines = [line]
        elif is_anchor and not md_match:
            _flush()
            current_anchor = stripped[:64]
            current_title = stripped[:64]
            current_lines = [line]
        elif md_match and int(len(md_match.group(1))) <= 2:
            # Major heading without traditional anchor — still a section break
            _flush()
            current_anchor = stripped[:64]
            current_title = md_match.group(2).strip()[:64]
            current_lines = [line]
        else:
            if current_anchor is None:
                # Preamble before first section
                current_anchor = "前言"
                current_title = "前言"
            current_lines.append(line)

    _flush()

    if not sections and markdown_text.strip():
        sections.append(
            TenderSection(
                section_id="S-000",
                anchor="全文",
                title="全文",
                content=markdown_text.strip()[:50000],
            )
        )

    logger.info("sectionized markdown into %d sections", len(sections))
    return TenderSections(sections=sections)
