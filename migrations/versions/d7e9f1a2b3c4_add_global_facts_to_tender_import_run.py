"""Add global_facts column to tender_import_run

Revision ID: d7e9f1a2b3c4
Revises: 8d3f1c2e5ab0
Create Date: 2026-02-25 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e9f1a2b3c4"
down_revision: str | Sequence[str] | None = "c1d2e3f4g5h6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tender_import_run",
        sa.Column("global_facts", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tender_import_run", "global_facts")
