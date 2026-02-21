"""V1.1 JSONB+GIN and workflow resume fields

Revision ID: 1f3c9d8a7b61
Revises: 8d3f1c2e5ab0
Create Date: 2026-02-21 18:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1f3c9d8a7b61"
down_revision: str | Sequence[str] | None = "8d3f1c2e5ab0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ensure_workflow_run_table_postgres() -> None:
    op.create_table(
        "workflow_run",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sections_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("section_status_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=False, server_default="G0"),
        sa.Column("step_status", sa.Text(), nullable=False, server_default="paused"),
        sa.Column("resume_from_step", sa.Text(), nullable=False, server_default="G1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if dialect == "postgresql":
        if not inspector.has_table("workflow_run"):
            _ensure_workflow_run_table_postgres()
        else:
            op.add_column("workflow_run", sa.Column("current_step", sa.Text(), nullable=False, server_default="G0"))
            op.add_column("workflow_run", sa.Column("step_status", sa.Text(), nullable=False, server_default="paused"))
            op.add_column(
                "workflow_run",
                sa.Column("resume_from_step", sa.Text(), nullable=False, server_default="G1"),
            )
            op.add_column("workflow_run", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
            op.add_column("workflow_run", sa.Column("last_error", sa.Text(), nullable=True))

        if "parent_chunk_id" not in {col["name"] for col in inspector.get_columns("evidence_chunk")}:
            op.add_column("evidence_chunk", sa.Column("parent_chunk_id", sa.Text(), nullable=True))
        if "anchor_type" not in {col["name"] for col in inspector.get_columns("evidence_chunk")}:
            op.add_column("evidence_chunk", sa.Column("anchor_type", sa.Text(), nullable=True))

        json_columns = [
            ("workflow_run", "sections_json"),
            ("workflow_run", "section_status_json"),
            ("doc_block", "content_json"),
            ("section_content", "content_json"),
            ("ingest_job", "report_json"),
            ("audit_log", "metadata"),
            ("tender_analysis_run", "summary_json"),
            ("review_report", "report_json"),
            ("scoring_report", "details_json"),
        ]

        for table, column in json_columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSONB USING {column}::JSONB")
            op.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_{column}_gin ON {table} USING GIN ({column})"
            )
    else:
        if inspector.has_table("workflow_run"):
            columns = {col["name"] for col in inspector.get_columns("workflow_run")}
            if "current_step" not in columns:
                op.add_column("workflow_run", sa.Column("current_step", sa.Text(), nullable=False, server_default="G0"))
            if "step_status" not in columns:
                op.add_column("workflow_run", sa.Column("step_status", sa.Text(), nullable=False, server_default="paused"))
            if "resume_from_step" not in columns:
                op.add_column(
                    "workflow_run",
                    sa.Column("resume_from_step", sa.Text(), nullable=False, server_default="G1"),
                )
            if "retry_count" not in columns:
                op.add_column("workflow_run", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
            if "last_error" not in columns:
                op.add_column("workflow_run", sa.Column("last_error", sa.Text(), nullable=True))

        if inspector.has_table("evidence_chunk"):
            columns = {col["name"] for col in inspector.get_columns("evidence_chunk")}
            if "parent_chunk_id" not in columns:
                op.add_column("evidence_chunk", sa.Column("parent_chunk_id", sa.Text(), nullable=True))
            if "anchor_type" not in columns:
                op.add_column("evidence_chunk", sa.Column("anchor_type", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("evidence_chunk"):
        columns = {col["name"] for col in inspector.get_columns("evidence_chunk")}
        if "anchor_type" in columns:
            op.drop_column("evidence_chunk", "anchor_type")
        if "parent_chunk_id" in columns:
            op.drop_column("evidence_chunk", "parent_chunk_id")

    if inspector.has_table("workflow_run"):
        columns = {col["name"] for col in inspector.get_columns("workflow_run")}
        if "last_error" in columns:
            op.drop_column("workflow_run", "last_error")
        if "retry_count" in columns:
            op.drop_column("workflow_run", "retry_count")
        if "resume_from_step" in columns:
            op.drop_column("workflow_run", "resume_from_step")
        if "step_status" in columns:
            op.drop_column("workflow_run", "step_status")
        if "current_step" in columns:
            op.drop_column("workflow_run", "current_step")
