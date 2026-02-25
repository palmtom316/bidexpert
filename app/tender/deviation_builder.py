"""Deviation table builder — generates deviation entries from technical tracking (R2)."""

from __future__ import annotations

import logging

from app.tender.schemas import DeviationEntry, DeviationTables

logger = logging.getLogger(__name__)


def build_deviation_tables(tech_data: dict) -> DeviationTables:
    """Build deviation tables from technical requirements with deviation_tracking.

    R2: Deviation tables must be generated before any writing begins.
    """
    commercial: list[DeviationEntry] = []
    technical: list[DeviationEntry] = []

    for req in tech_data.get("requirements", []):
        req_id = req.get("req_id", "")
        desc = req.get("description", "")
        tracking = req.get("deviation_tracking", "")
        is_mandatory = req.get("is_mandatory", False)
        category = req.get("category", "general")

        if not desc:
            continue

        entry = DeviationEntry(
            req_id=req_id,
            requirement_text=desc[:500],
            response_status="PENDING",
            deviation_type=None,
            deviation_detail=None,
            risk_level="high" if is_mandatory else "medium",
        )

        # Route to commercial or technical based on category
        if category in ("schedule", "pricing", "contract"):
            commercial.append(entry)
        else:
            technical.append(entry)

    logger.info(
        "deviation tables: %d commercial, %d technical entries",
        len(commercial), len(technical),
    )
    return DeviationTables(
        commercial_deviations=commercial,
        technical_deviations=technical,
    )
