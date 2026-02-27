"""Asset repository — query company qualifications, personnel, performance.

Uses SQL hard filters (R3, R4) against existing expert_doc + evidence_chunk tables.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models.tables import BidAssetPool, ExpertDoc

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def list_bid_asset_pool_entries(
    db: Session,
    *,
    project_id: uuid.UUID,
    ownership_roles: list[str] | None = None,
    asset_type: str | None = None,
) -> list[BidAssetPool]:
    stmt = select(BidAssetPool).where(BidAssetPool.project_id == project_id)
    if ownership_roles:
        normalized_roles = [role.strip() for role in ownership_roles if role and role.strip()]
        if normalized_roles:
            stmt = stmt.where(BidAssetPool.ownership_role.in_(normalized_roles))
    rows = db.execute(stmt).scalars().all()
    if not asset_type:
        return rows
    normalized_type = asset_type.strip().lower()
    return [
        row
        for row in rows
        if isinstance(row.metadata_json, dict)
        and str(row.metadata_json.get("asset_type", "")).strip().lower() == normalized_type
    ]


def list_personnel_candidates_from_asset_pool(
    db: Session,
    *,
    project_id: uuid.UUID,
    ownership_roles: list[str] | None = None,
    role: str | None = None,
    no_active_project: bool = False,
    social_security_months: int | None = None,
) -> list[dict[str, Any]]:
    rows = list_bid_asset_pool_entries(
        db,
        project_id=project_id,
        ownership_roles=ownership_roles,
        asset_type="person",
    )
    normalized_role = (role or "").strip()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        metadata = dict(row.metadata_json or {})
        roles = metadata.get("roles")
        role_list = [str(item).strip() for item in roles] if isinstance(roles, list) else []
        if normalized_role and normalized_role not in role_list:
            continue

        months = _safe_int(metadata.get("social_security_months"), default=0)
        if social_security_months is not None and months < int(social_security_months):
            continue

        active_project_count = _safe_int(metadata.get("active_project_count"), default=0)
        if no_active_project and active_project_count > 0:
            continue

        evidence_refs = metadata.get("evidence_refs")
        evidence_list = evidence_refs if isinstance(evidence_refs, list) else []

        candidates.append(
            {
                "asset_pool_id": row.id,
                "project_id": row.project_id,
                "asset_name": row.asset_name,
                "ownership_role": row.ownership_role,
                "roles": role_list,
                "social_security_months": months,
                "active_project_count": active_project_count,
                "match_score": _safe_float(metadata.get("match_score", metadata.get("score", 0.0)), default=0.0),
                "evidence_refs": evidence_list,
            }
        )
    return candidates
