"""Align completed_bid.project_id to UUID foreign key

Revision ID: 9b7c1f0a2d44
Revises: 6d8b5df4f2ab
Create Date: 2026-02-23 15:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b7c1f0a2d44"
down_revision: str | Sequence[str] | None = "6d8b5df4f2ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_completed_bid_project_id_project"


def _has_project_fk(inspector: sa.Inspector) -> bool:
    for fk in inspector.get_foreign_keys("completed_bid"):
        constrained = fk.get("constrained_columns") or []
        referred = fk.get("referred_columns") or []
        if (
            fk.get("referred_table") == "project"
            and constrained == ["project_id"]
            and referred == ["id"]
        ):
            return True
    return False


def _column_is_uuid(inspector: sa.Inspector) -> bool:
    for column in inspector.get_columns("completed_bid"):
        if column.get("name") != "project_id":
            continue
        type_name = str(column.get("type", "")).upper()
        return "UUID" in type_name
    return False


def _column_nullable(inspector: sa.Inspector) -> bool:
    for column in inspector.get_columns("completed_bid"):
        if column.get("name") == "project_id":
            return bool(column.get("nullable", True))
    return True


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("completed_bid") or not inspector.has_table("project"):
        return

    needs_type = not _column_is_uuid(inspector)
    needs_fk = not _has_project_fk(inspector)
    nullable = _column_nullable(inspector)
    if not needs_type and not needs_fk:
        return

    if bind.dialect.name == "postgresql":
        if needs_type:
            op.execute(
                sa.text(
                    "UPDATE completed_bid "
                    "SET project_id = NULL "
                    "WHERE project_id IS NOT NULL "
                    "AND project_id::text !~* "
                    "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"
                )
            )
            op.execute(
                sa.text(
                    "ALTER TABLE completed_bid "
                    "ALTER COLUMN project_id TYPE UUID USING project_id::uuid"
                )
            )
        if needs_fk:
            op.create_foreign_key(
                _FK_NAME,
                "completed_bid",
                "project",
                ["project_id"],
                ["id"],
                ondelete="SET NULL",
            )
        return

    with op.batch_alter_table("completed_bid", recreate="always") as batch_op:
        if needs_type:
            batch_op.alter_column(
                "project_id",
                existing_type=sa.Text(),
                type_=sa.UUID(),
                existing_nullable=nullable,
            )
        if needs_fk:
            batch_op.create_foreign_key(
                _FK_NAME,
                "project",
                ["project_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("completed_bid"):
        return

    has_fk = _has_project_fk(inspector)
    is_uuid = _column_is_uuid(inspector)
    nullable = _column_nullable(inspector)
    if not has_fk and not is_uuid:
        return

    if bind.dialect.name == "postgresql":
        if has_fk:
            op.drop_constraint(_FK_NAME, "completed_bid", type_="foreignkey")
        if is_uuid:
            op.execute(
                sa.text(
                    "ALTER TABLE completed_bid "
                    "ALTER COLUMN project_id TYPE TEXT USING project_id::text"
                )
            )
        return

    with op.batch_alter_table("completed_bid", recreate="always") as batch_op:
        if has_fk:
            batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        if is_uuid:
            batch_op.alter_column(
                "project_id",
                existing_type=sa.UUID(),
                type_=sa.Text(),
                existing_nullable=nullable,
            )
