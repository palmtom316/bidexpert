"""add methodology runs and snippets

Revision ID: 9f2c7a4d1b30
Revises: 6d8b5df4f2ab, c1d2e3f4g5h6
Create Date: 2026-02-25 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2c7a4d1b30"
down_revision: str | Sequence[str] | None = ("6d8b5df4f2ab", "c1d2e3f4g5h6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "methodology_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="RECEIVED"),
        sa.Column("step", sa.Text(), nullable=False, server_default="RECEIVED"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("input_kind", sa.Text(), nullable=False, server_default="text"),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("sanitized_input_path", sa.Text(), nullable=True),
        sa.Column("output_json_path", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("similarity_score", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("pii_removed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("findings_json", sa.JSON(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("reviewer", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_methodology_run_review_status", "methodology_run", ["review_status"])
    op.create_index("idx_methodology_run_risk_level", "methodology_run", ["risk_level"])
    op.create_index("idx_methodology_run_created_at", "methodology_run", ["created_at"])

    op.create_table(
        "methodology_snippet",
        sa.Column("snippet_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("methodology_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("applicability", sa.JSON(), nullable=True),
        sa.Column("structure", sa.JSON(), nullable=True),
        sa.Column("template_md", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("risk_level", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="approved"),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="system"),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_methodology_snippet_domain", "methodology_snippet", ["domain"])
    op.create_index("idx_methodology_snippet_risk_level", "methodology_snippet", ["risk_level"])
    op.create_index("idx_methodology_snippet_created_at", "methodology_snippet", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_methodology_snippet_created_at", table_name="methodology_snippet")
    op.drop_index("idx_methodology_snippet_risk_level", table_name="methodology_snippet")
    op.drop_index("idx_methodology_snippet_domain", table_name="methodology_snippet")
    op.drop_table("methodology_snippet")

    op.drop_index("idx_methodology_run_created_at", table_name="methodology_run")
    op.drop_index("idx_methodology_run_risk_level", table_name="methodology_run")
    op.drop_index("idx_methodology_run_review_status", table_name="methodology_run")
    op.drop_table("methodology_run")
