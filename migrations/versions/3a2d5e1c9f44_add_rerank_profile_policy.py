"""Add rerank profile policy field

Revision ID: 3a2d5e1c9f44
Revises: 1f3c9d8a7b61
Create Date: 2026-02-22 09:40:00.000000

"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a2d5e1c9f44"
down_revision: str | Sequence[str] | None = "1f3c9d8a7b61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _with_rerank_limit(raw: object) -> tuple[dict[str, int], bool]:
    if isinstance(raw, dict):
        limits = dict(raw)
    elif isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            limits = dict(loaded) if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            limits = {}
    else:
        limits = {}
    if "rerank" in limits:
        return limits, False
    limits["rerank"] = 2
    return limits, True


def _without_rerank_limit(raw: object) -> tuple[dict[str, int], bool]:
    if isinstance(raw, dict):
        limits = dict(raw)
    elif isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            limits = dict(loaded) if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            limits = {}
    else:
        limits = {}
    if "rerank" not in limits:
        return limits, False
    limits.pop("rerank", None)
    return limits, True


def _patch_concurrency_limits(add_rerank: bool) -> None:
    bind = op.get_bind()
    table = sa.table(
        "project_model_policy",
        sa.column("project_id"),
        sa.column("concurrency_limits", sa.JSON()),
    )
    rows = bind.execute(sa.select(table.c.project_id, table.c.concurrency_limits)).all()
    for project_id, raw_limits in rows:
        if add_rerank:
            patched, changed = _with_rerank_limit(raw_limits)
        else:
            patched, changed = _without_rerank_limit(raw_limits)
        if not changed:
            continue
        bind.execute(
            sa.update(table)
            .where(table.c.project_id == project_id)
            .values(concurrency_limits=patched)
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("project_model_policy"):
        return

    columns = {col["name"] for col in inspector.get_columns("project_model_policy")}
    if "rerank_profile_id" not in columns:
        if bind.dialect.name == "sqlite":
            op.add_column(
                "project_model_policy",
                sa.Column("rerank_profile_id", sa.UUID(), nullable=True),
            )
        else:
            op.add_column(
                "project_model_policy",
                sa.Column(
                    "rerank_profile_id",
                    sa.UUID(),
                    sa.ForeignKey("provider_profile.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

    _patch_concurrency_limits(add_rerank=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("project_model_policy"):
        return

    _patch_concurrency_limits(add_rerank=False)

    columns = {col["name"] for col in inspector.get_columns("project_model_policy")}
    if "rerank_profile_id" in columns:
        op.drop_column("project_model_policy", "rerank_profile_id")
