"""Add v2.0 redline/scorecard/generation baseline tables.

Revision ID: 9b7c1d2e3f4a
Revises: e8c4f0a1b2c3
Create Date: 2026-02-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b7c1d2e3f4a"
down_revision: str | Sequence[str] | None = "e8c4f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tender_addendum",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("tender_id", sa.Text(), nullable=True),
        sa.Column("addendum_code", sa.Text(), nullable=True),
        sa.Column("parsed_overrides_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tender_addendum_project_id", "tender_addendum", ["project_id"], unique=False)

    op.create_table(
        "mandatory_clause",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("clause_code", sa.Text(), nullable=True),
        sa.Column("clause_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_mandatory_clause_project_id", "mandatory_clause", ["project_id"], unique=False)

    op.create_table(
        "bid_asset_pool",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_name", sa.Text(), nullable=False),
        sa.Column("ownership_role", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_bid_asset_pool_project_id", "bid_asset_pool", ["project_id"], unique=False)

    op.create_table(
        "chapter_evidence_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_key", sa.Text(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evidence_chunk_id"], ["evidence_chunk.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chapter_evidence_link_project_id", "chapter_evidence_link", ["project_id"], unique=False)
    op.create_index("idx_chapter_evidence_link_chapter_key", "chapter_evidence_link", ["chapter_key"], unique=False)

    op.create_table(
        "generation_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=False, server_default="RECEIVED"),
        sa.Column("step_status", sa.Text(), nullable=False, server_default="paused"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resume_from_step", sa.Text(), nullable=False, server_default="RECEIVED"),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generation_run_project_id", "generation_run", ["project_id"], unique=False)
    op.create_index(
        "idx_generation_run_project_created_at",
        "generation_run",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_generation_run_status_created_at",
        "generation_run",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "score_evaluation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("score_total", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_score_evaluation_generation_run_id",
        "score_evaluation",
        ["generation_run_id"],
        unique=False,
    )
    op.create_index("idx_score_evaluation_project_id", "score_evaluation", ["project_id"], unique=False)

    op.create_table(
        "compliance_report",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_compliance_report_generation_run_id",
        "compliance_report",
        ["generation_run_id"],
        unique=False,
    )
    op.create_index("idx_compliance_report_project_id", "compliance_report", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_compliance_report_project_id", table_name="compliance_report")
    op.drop_index("idx_compliance_report_generation_run_id", table_name="compliance_report")
    op.drop_table("compliance_report")

    op.drop_index("idx_score_evaluation_project_id", table_name="score_evaluation")
    op.drop_index("idx_score_evaluation_generation_run_id", table_name="score_evaluation")
    op.drop_table("score_evaluation")

    op.drop_index("idx_generation_run_status_created_at", table_name="generation_run")
    op.drop_index("idx_generation_run_project_created_at", table_name="generation_run")
    op.drop_index("idx_generation_run_project_id", table_name="generation_run")
    op.drop_table("generation_run")

    op.drop_index("idx_chapter_evidence_link_chapter_key", table_name="chapter_evidence_link")
    op.drop_index("idx_chapter_evidence_link_project_id", table_name="chapter_evidence_link")
    op.drop_table("chapter_evidence_link")

    op.drop_index("idx_bid_asset_pool_project_id", table_name="bid_asset_pool")
    op.drop_table("bid_asset_pool")

    op.drop_index("idx_mandatory_clause_project_id", table_name="mandatory_clause")
    op.drop_table("mandatory_clause")

    op.drop_index("idx_tender_addendum_project_id", table_name="tender_addendum")
    op.drop_table("tender_addendum")
