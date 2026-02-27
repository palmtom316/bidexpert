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

_PERFORMANCE_TABLE_TEMPLATE = Template(
    """| 项目名称 | 合同金额(万元) | 工程类型 | 建设单位 | 竣工日期 | 证据 |
| --- | --- | --- | --- | --- | --- |
{% for row in rows -%}
| {{ row.project_name }} | {{ row.contract_amount }} | {{ row.engineering_type }} | {{ row.client }} | {{ row.completion_date }} | {{ row.evidence }} |
{% endfor %}"""
)

_EQUIPMENT_TABLE_TEMPLATE = Template(
    """| 设备名称 | 规格型号 | 数量 | 技术参数 | 归属角色 | 证据 |
| --- | --- | --- | --- | --- | --- |
{% for row in rows -%}
| {{ row.equipment_name }} | {{ row.spec_model }} | {{ row.quantity }} | {{ row.tech_params }} | {{ row.ownership_role }} | {{ row.evidence }} |
{% endfor %}"""
)

_EMPTY_PERFORMANCE = "| 项目名称 | 合同金额(万元) | 工程类型 | 建设单位 | 竣工日期 | 证据 |\n| --- | --- | --- | --- | --- | --- |\n| (无) | - | - | - | - | - |"
_EMPTY_EQUIPMENT = "| 设备名称 | 规格型号 | 数量 | 技术参数 | 归属角色 | 证据 |\n| --- | --- | --- | --- | --- | --- |\n| (无) | - | - | - | - | - |"
_EMPTY_GENERIC = "| 资产名称 | 归属角色 | 资产类型 | 证据 |\n| --- | --- | --- | --- |\n| (无) | - | - | - |"


def _build_performance_rows(items: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        metadata = dict(item.get("metadata") or {})
        evidence_refs = metadata.get("evidence_refs")
        evidence = "、".join(str(v) for v in evidence_refs) if isinstance(evidence_refs, list) else ""
        rows.append(
            {
                "project_name": str(item.get("asset_name", "")),
                "contract_amount": str(metadata.get("contract_amount", "")),
                "engineering_type": str(metadata.get("engineering_type", "")),
                "client": str(metadata.get("client", "")),
                "completion_date": str(metadata.get("completion_date", "")),
                "evidence": evidence,
            }
        )
    rows.sort(key=lambda r: r["project_name"])
    return rows


def _build_equipment_rows(items: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        metadata = dict(item.get("metadata") or {})
        evidence_refs = metadata.get("evidence_refs")
        evidence = "、".join(str(v) for v in evidence_refs) if isinstance(evidence_refs, list) else ""
        rows.append(
            {
                "equipment_name": str(item.get("asset_name", "")),
                "spec_model": str(metadata.get("spec_model", "")),
                "quantity": str(metadata.get("quantity", "")),
                "tech_params": str(metadata.get("tech_params", "")),
                "ownership_role": str(item.get("ownership_role", "")),
                "evidence": evidence,
            }
        )
    rows.sort(key=lambda r: r["equipment_name"])
    return rows


def _build_generic_rows(items: list[dict], asset_type: str) -> list[dict[str, str]]:
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
    return rows


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

    if asset_type == "performance":
        rows = _build_performance_rows(items)
        if not rows:
            return _EMPTY_PERFORMANCE
        return _PERFORMANCE_TABLE_TEMPLATE.render(rows=rows).strip()

    if asset_type == "equipment":
        rows = _build_equipment_rows(items)
        if not rows:
            return _EMPTY_EQUIPMENT
        return _EQUIPMENT_TABLE_TEMPLATE.render(rows=rows).strip()

    # Generic fallback
    rows = _build_generic_rows(items, asset_type)
    if not rows:
        return _EMPTY_GENERIC
    return _TABLE_TEMPLATE.render(rows=rows).strip()
