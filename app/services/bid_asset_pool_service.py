from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.tender.assets.repository import list_bid_asset_pool_entries


def list_project_asset_pool(
    db: Session,
    *,
    project_id: uuid.UUID,
    ownership_roles: list[str] | None = None,
    asset_type: str | None = None,
) -> list[dict[str, Any]]:
    rows = list_bid_asset_pool_entries(
        db,
        project_id=project_id,
        ownership_roles=ownership_roles,
        asset_type=asset_type,
    )
    return [
        {
            "asset_pool_id": row.id,
            "project_id": row.project_id,
            "asset_name": row.asset_name,
            "ownership_role": row.ownership_role,
            "metadata": dict(row.metadata_json or {}),
        }
        for row in rows
    ]


def ensure_project_asset_isolation(
    db: Session,
    *,
    project_id: uuid.UUID,
    asset_pool_ids: list[uuid.UUID],
) -> bool:
    if not asset_pool_ids:
        return True

    rows = list_bid_asset_pool_entries(db, project_id=project_id)
    allowed = {row.id for row in rows}
    return all(asset_id in allowed for asset_id in asset_pool_ids)
