"""Merge heads and add audit/tender indexes.

Revision ID: e8c4f0a1b2c3
Revises: 6d8b5df4f2ab, c1d2e3f4g5h6, d7e9f1a2b3c4
Create Date: 2026-02-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c4f0a1b2c3"
down_revision: str | Sequence[str] | None = ("6d8b5df4f2ab", "d7e9f1a2b3c4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {idx.get("name", "") for idx in inspector.get_indexes(table_name) if idx.get("name")}
    except Exception:  # pragma: no cover
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("audit_log"):
        existing = _index_names(inspector, "audit_log")
        if "idx_audit_log_project_created_at" not in existing:
            op.create_index(
                "idx_audit_log_project_created_at",
                "audit_log",
                ["project_id", "created_at"],
                unique=False,
            )
        if "idx_audit_log_action_created_at" not in existing:
            op.create_index(
                "idx_audit_log_action_created_at",
                "audit_log",
                ["action", "created_at"],
                unique=False,
            )

    if inspector.has_table("tender_import_run"):
        existing = _index_names(inspector, "tender_import_run")
        if "idx_tender_import_run_project_created_at" not in existing:
            op.create_index(
                "idx_tender_import_run_project_created_at",
                "tender_import_run",
                ["project_id", "created_at"],
                unique=False,
            )
        if "idx_tender_import_run_tender_created_at" not in existing:
            op.create_index(
                "idx_tender_import_run_tender_created_at",
                "tender_import_run",
                ["tender_id", "created_at"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tender_import_run"):
        existing = _index_names(inspector, "tender_import_run")
        if "idx_tender_import_run_tender_created_at" in existing:
            op.drop_index("idx_tender_import_run_tender_created_at", table_name="tender_import_run")
        if "idx_tender_import_run_project_created_at" in existing:
            op.drop_index("idx_tender_import_run_project_created_at", table_name="tender_import_run")

    if inspector.has_table("audit_log"):
        existing = _index_names(inspector, "audit_log")
        if "idx_audit_log_action_created_at" in existing:
            op.drop_index("idx_audit_log_action_created_at", table_name="audit_log")
        if "idx_audit_log_project_created_at" in existing:
            op.drop_index("idx_audit_log_project_created_at", table_name="audit_log")

