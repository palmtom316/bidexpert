"""v1.4 — Lifecycle Red-Line Control.

Asset expiration dates + standard version management.
Auto-deprecate old standards when newer versions are ingested.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from sqlalchemy import select, update

from app.db.session import session_scope
from app.models.tables import EvidenceChunk, ExpertDoc

logger = logging.getLogger(__name__)

# Common Chinese national / industry standard code patterns
_STANDARD_CODE_RE = re.compile(
    r"(GB|GB/T|DL|DL/T|JGJ|JB|NB|NB/T|SL|YD|HJ|CJJ|JT|Q/GDW|CECS|IEEE|IEC)"
    r"\s*[-/]?\s*(\d{3,6})",
    re.IGNORECASE,
)
_VERSION_YEAR_RE = re.compile(r"[-—./\s]*((?:19|20)\d{2})\b")


@dataclass
class StandardCheckResult:
    standard_code: str
    version_year: int
    is_latest: bool
    existing_versions: list[int] = field(default_factory=list)
    deprecated_count: int = 0


def detect_standard_info(text: str) -> tuple[str | None, int | None]:
    """Extract standard_code and version_year from document text (first 2000 chars)."""
    snippet = (text or "")[:2000]
    code_match = _STANDARD_CODE_RE.search(snippet)
    if not code_match:
        return None, None
    standard_code = f"{code_match.group(1)}{code_match.group(2)}".upper().replace(" ", "")
    # Look for year near the code
    remainder = snippet[code_match.end():][:30]
    year_match = _VERSION_YEAR_RE.search(remainder)
    version_year = int(year_match.group(1)) if year_match else None
    return standard_code, version_year


def validate_asset_lifecycle(
    expiration_date: date | None,
    valid_to: date | None = None,
) -> bool:
    """Check if asset is still valid (not expired).

    Returns True if valid, False if expired.
    """
    today = date.today()
    if expiration_date and expiration_date < today:
        return False
    if valid_to and valid_to < today:
        return False
    return True


def validate_standard_version(standard_code: str, version_year: int) -> StandardCheckResult:
    """Check if version is the latest for this standard_code in the DB."""
    with session_scope() as db:
        rows = db.execute(
            select(ExpertDoc.version_year)
            .where(ExpertDoc.standard_code == standard_code)
            .where(ExpertDoc.standard_status == "active")
            .where(ExpertDoc.version_year.is_not(None))
        ).scalars().all()

    existing_years = sorted({int(y) for y in rows if y is not None})
    is_latest = not existing_years or version_year >= max(existing_years)
    return StandardCheckResult(
        standard_code=standard_code,
        version_year=version_year,
        is_latest=is_latest,
        existing_versions=existing_years,
    )


def auto_deprecate_old_versions(standard_code: str, new_version_year: int) -> int:
    """Mark older versions of a standard as 'deprecated' in both ExpertDoc and EvidenceChunk."""
    deprecated_count = 0
    with session_scope() as db:
        # Find ExpertDoc records with older version_year
        old_docs = db.execute(
            select(ExpertDoc.id)
            .where(ExpertDoc.standard_code == standard_code)
            .where(ExpertDoc.standard_status == "active")
            .where(ExpertDoc.version_year < new_version_year)
        ).scalars().all()

        if not old_docs:
            return 0

        old_doc_ids = list(old_docs)

        # Deprecate ExpertDoc records
        db.execute(
            update(ExpertDoc)
            .where(ExpertDoc.id.in_(old_doc_ids))
            .values(standard_status="deprecated")
        )

        # Deprecate associated EvidenceChunk records
        db.execute(
            update(EvidenceChunk)
            .where(EvidenceChunk.expert_doc_id.in_(old_doc_ids))
            .values(standard_status="deprecated")
        )

        db.commit()
        deprecated_count = len(old_doc_ids)

    if deprecated_count > 0:
        logger.info(
            "auto-deprecated %d older docs for standard %s (new year=%d)",
            deprecated_count,
            standard_code,
            new_version_year,
        )
    return deprecated_count


def filter_expired_assets(query):
    """Add SQL-layer filter to exclude expired records from a query on ExpertDoc."""
    today = date.today()
    return query.where(
        (ExpertDoc.expiration_date.is_(None)) | (ExpertDoc.expiration_date >= today)
    ).where(
        ExpertDoc.standard_status == "active"
    )


def get_active_standards(standard_code: str) -> list[dict]:
    """Return only active standard versions for a given standard_code."""
    with session_scope() as db:
        rows = db.execute(
            select(
                ExpertDoc.id,
                ExpertDoc.title,
                ExpertDoc.version_year,
                ExpertDoc.standard_status,
                ExpertDoc.expiration_date,
            )
            .where(ExpertDoc.standard_code == standard_code)
            .where(ExpertDoc.standard_status == "active")
            .order_by(ExpertDoc.version_year.desc())
        ).all()

    return [
        {
            "id": str(row.id),
            "title": row.title,
            "version_year": row.version_year,
            "standard_status": row.standard_status,
            "expiration_date": str(row.expiration_date) if row.expiration_date else None,
        }
        for row in rows
    ]
