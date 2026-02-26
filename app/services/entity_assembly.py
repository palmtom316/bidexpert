from __future__ import annotations

import uuid

from jinja2 import Template
from sqlalchemy.orm import Session

from app.services.bid_asset_pool_service import list_project_asset_pool

_TABLE_TEMPLATE = Template(
    """| 资产名称 | 归属角色 | 资产类型 | 证据 |
| --- | --- | --- | --- |
{% for row in rows -%}
| {{ row.asset_name }} | {{ row.ownership_role }} | {{ row.asset_type }} | {{ row.evidence }} |
{% endfor %}"""
)


def render_bid_asset_pool_markdown_table(
    db: Session,
    *,
    project_id: uuid.UUID,
    asset_type: str,
    ownership_roles: list[str] | None = None,
) -> str:
    items = list_project_asset_pool(
        db,
        project_id=project_id,
        ownership_roles=ownership_roles,
        asset_type=asset_type,
    )
    rows: list[dict[str, str]] = []
    for item in items:
        metadata = dict(item.get("metadata") or {})
        evidence_refs = metadata.get("evidence_refs")
        evidence = "、".join(str(v) for v in evidence_refs) if isinstance(evidence_refs, list) else ""
        rows.append(
            {
                "asset_name": str(item.get("asset_name", "")),
                "ownership_role": str(item.get("ownership_role", "")),
                "asset_type": str(metadata.get("asset_type", asset_type)),
                "evidence": evidence,
            }
        )
    rows.sort(key=lambda row: (row["asset_name"], row["ownership_role"], row["asset_type"], row["evidence"]))

    if not rows:
        return "| 资产名称 | 归属角色 | 资产类型 | 证据 |\n| --- | --- | --- | --- |\n| (无) | - | - | - |"

    return _TABLE_TEMPLATE.render(rows=rows).strip()
