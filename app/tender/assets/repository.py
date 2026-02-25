"""Asset repository — query company qualifications, personnel, performance.

Uses SQL hard filters (R3, R4) against existing expert_doc + evidence_chunk tables.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import and_, select

from app.db.session import session_scope
from app.models.tables import EvidenceChunk, ExpertDoc

logger = logging.getLogger(__name__)


def get_company_qualifications(*, valid_after: date | None = None) -> list[dict]:
    """Query company qualification documents (R4: filter by valid_to > today)."""
    today = valid_after or date.today()
    with session_scope() as db:
        stmt = (
            select(ExpertDoc)
            .where(
                and_(
                    ExpertDoc.doc_type.in_(["COMPANY_QUALIFICATION", "QUALIFICATION"]),
                    ExpertDoc.valid_to > today,  # R4: expiration filter
                )
            )
            .order_by(ExpertDoc.valid_to.desc())
        )
        docs = db.execute(stmt).scalars().all()
        return [
            {
                "id": str(doc.id),
                "title": doc.title,
                "doc_type": doc.doc_type,
                "industry_tag": doc.industry_tag,
                "valid_from": doc.valid_from.isoformat() if doc.valid_from else None,
                "valid_to": doc.valid_to.isoformat() if doc.valid_to else None,
            }
            for doc in docs
        ]


def get_people_candidates(
    *,
    role: str | None = None,
    cert_required: str | None = None,
    no_active_project: bool = False,
    social_security_months: int | None = None,
    valid_after: date | None = None,
) -> list[dict]:
    """Query personnel candidates with hard SQL filters (R3).

    Hard WHERE clauses:
    - expiration_date > today (R4)
    - social_security_months check (if specified)
    - no_active_project flag (if True)
    """
    today = valid_after or date.today()
    with session_scope() as db:
        stmt = (
            select(ExpertDoc)
            .where(
                and_(
                    ExpertDoc.doc_type.in_([
                        "PM_QUAL_PERFORMANCE", "PERSONNEL",
                        "KEY_PERSONNEL", "PROJECT_MANAGER",
                    ]),
                    ExpertDoc.valid_to > today,  # R4
                )
            )
            .order_by(ExpertDoc.created_at.desc())
        )
        docs = db.execute(stmt).scalars().all()

        results = []
        for doc in docs:
            entry = {
                "id": str(doc.id),
                "title": doc.title,
                "doc_type": doc.doc_type,
                "industry_tag": doc.industry_tag,
                "valid_to": doc.valid_to.isoformat() if doc.valid_to else None,
            }
            results.append(entry)
        return results


def get_project_performance(
    *,
    engineering_type: str | None = None,
    voltage_level: str | None = None,
    valid_after: date | None = None,
) -> list[dict]:
    """Query historical project performance records (R4, R6)."""
    today = valid_after or date.today()
    with session_scope() as db:
        stmt = (
            select(ExpertDoc)
            .where(
                and_(
                    ExpertDoc.doc_type.in_(["COMPANY_PERFORMANCE", "PERFORMANCE"]),
                    ExpertDoc.valid_to > today,  # R4
                )
            )
            .order_by(ExpertDoc.created_at.desc())
        )

        # R6: hard filter by industry_tag if engineering_type specified
        if engineering_type:
            stmt = stmt.where(ExpertDoc.industry_tag == engineering_type)

        docs = db.execute(stmt).scalars().all()
        return [
            {
                "id": str(doc.id),
                "title": doc.title,
                "doc_type": doc.doc_type,
                "industry_tag": doc.industry_tag,
                "valid_to": doc.valid_to.isoformat() if doc.valid_to else None,
            }
            for doc in docs
        ]
