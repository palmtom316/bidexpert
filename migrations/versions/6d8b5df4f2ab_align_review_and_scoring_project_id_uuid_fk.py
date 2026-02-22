"""Align review/scoring report project_id to UUID FK

Revision ID: 6d8b5df4f2ab
Revises: 3a2d5e1c9f44
Create Date: 2026-02-22 12:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d8b5df4f2ab"
down_revision: str | Sequence[str] | None = "3a2d5e1c9f44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVIEW_FK_NAME = "fk_review_report_project_id_project"
_SCORING_FK_NAME = "fk_scoring_report_project_id_project"


def _has_project_fk(inspector: sa.Inspector, table_name: str) -> bool:
    for fk in inspector.get_foreign_keys(table_name):
        constrained = fk.get("constrained_columns") or []
        referred = fk.get("referred_columns") or []
        if (
            fk.get("referred_table") == "project"
            and constrained == ["project_id"]
            and referred == ["id"]
        ):
            return True
    return False


def _column_is_uuid(inspector: sa.Inspector, table_name: str) -> bool:
    for column in inspector.get_columns(table_name):
        if column.get("name") != "project_id":
            continue
        type_name = str(column.get("type", "")).upper()
        return "UUID" in type_name
    return False


def _column_nullable(inspector: sa.Inspector, table_name: str) -> bool:
    for column in inspector.get_columns(table_name):
        if column.get("name") == "project_id":
            return bool(column.get("nullable", True))
    return True


def _ensure_review_report_index() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("review_report"):
        return
    indexes = {idx.get("name") for idx in inspector.get_indexes("review_report")}
    if "idx_review_report_project_section" not in indexes:
        op.create_index(
            "idx_review_report_project_section",
            "review_report",
            ["project_id", "section_key"],
            unique=False,
        )


def _upgrade_table(table_name: str, fk_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name) or not inspector.has_table("project"):
        return

    needs_type = not _column_is_uuid(inspector, table_name)
    needs_fk = not _has_project_fk(inspector, table_name)
    nullable = _column_nullable(inspector, table_name)
    if not needs_type and not needs_fk:
        return

    if bind.dialect.name == "postgresql":
        if needs_type:
            op.execute(
                sa.text(
                    f"ALTER TABLE {table_name} ALTER COLUMN project_id TYPE UUID USING project_id::uuid"
                )
            )
        if needs_fk:
            op.create_foreign_key(
                fk_name,
                table_name,
                "project",
                ["project_id"],
                ["id"],
                ondelete="CASCADE",
            )
        return

    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        if needs_type:
            batch_op.alter_column(
                "project_id",
                existing_type=sa.Text(),
                type_=sa.UUID(),
                existing_nullable=nullable,
            )
        if needs_fk:
            batch_op.create_foreign_key(
                fk_name,
                "project",
                ["project_id"],
                ["id"],
                ondelete="CASCADE",
            )


def _downgrade_table(table_name: str, fk_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return

    has_fk = _has_project_fk(inspector, table_name)
    is_uuid = _column_is_uuid(inspector, table_name)
    nullable = _column_nullable(inspector, table_name)
    if not has_fk and not is_uuid:
        return

    if bind.dialect.name == "postgresql":
        if has_fk:
            op.drop_constraint(fk_name, table_name, type_="foreignkey")
        if is_uuid:
            op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN project_id TYPE TEXT USING project_id::text"))
        return

    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        if has_fk:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        if is_uuid:
            batch_op.alter_column(
                "project_id",
                existing_type=sa.UUID(),
                type_=sa.Text(),
                existing_nullable=nullable,
            )


def upgrade() -> None:
    _upgrade_table("review_report", _REVIEW_FK_NAME)
    _upgrade_table("scoring_report", _SCORING_FK_NAME)
    _ensure_review_report_index()


def downgrade() -> None:
    _downgrade_table("scoring_report", _SCORING_FK_NAME)
    _downgrade_table("review_report", _REVIEW_FK_NAME)
    _ensure_review_report_index()
