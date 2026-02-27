"""Add tender_import_run table for v1.1 pipeline

Revision ID: b5c8d3e6f7a1
Revises: a4b7c2d1e3f5
Create Date: 2026-02-25 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c8d3e6f7a1"
down_revision: str | Sequence[str] | None = "a4b7c2d1e3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STEP_VALUES = (
    "RECEIVED", "UNPACKED", "VALIDATED", "SECTIONIZED",
    "PRELIM_EXTRACTED", "FATAL_GATE_CHECKED",
    "SCORING_EXTRACTED", "TECH_EXTRACTED",
    "DEVIATION_BUILT", "FORMAT_SIGNATURE_EXTRACTED",
    "BLUEPRINT_BUILT", "READY_FOR_WRITING",
    "FATAL_BLOCKED", "FAILED",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # if dialect == "postgresql":
    #     # Create enum type first
    #     step_enum = sa.Enum(*_STEP_VALUES, name="tender_run_step")
    #     step_enum.create(bind, checkfirst=True)

    op.create_table(
        "tender_import_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tender_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column(
            "current_step",
            sa.Enum(*_STEP_VALUES, name="tender_run_step", create_constraint=True),
            nullable=False,
            server_default="RECEIVED",
        ),
        sa.Column("fatal_blocked_reason", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_tender_import_run_project_id", "tender_import_run", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("idx_tender_import_run_project_id", table_name="tender_import_run")
    op.drop_table("tender_import_run")

    if dialect == "postgresql":
        sa.Enum(name="tender_run_step").drop(bind, checkfirst=True)
