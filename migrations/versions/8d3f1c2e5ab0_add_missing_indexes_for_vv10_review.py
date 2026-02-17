"""Add missing indexes for VV1.0 review fixes

Revision ID: 8d3f1c2e5ab0
Revises: 47ace6ac701b
Create Date: 2026-02-17 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d3f1c2e5ab0"
down_revision: str | Sequence[str] | None = "47ace6ac701b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_section_content_project_section_key",
        "section_content",
        ["project_id", "section_key"],
        unique=False,
    )
    op.create_index(
        "idx_llm_call_log_project_id",
        "llm_call_log",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "idx_compliance_matrix_project_id",
        "compliance_matrix",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "idx_review_report_project_section",
        "review_report",
        ["project_id", "section_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_review_report_project_section", table_name="review_report")
    op.drop_index("idx_compliance_matrix_project_id", table_name="compliance_matrix")
    op.drop_index("idx_llm_call_log_project_id", table_name="llm_call_log")
    op.drop_index("idx_section_content_project_section_key", table_name="section_content")
