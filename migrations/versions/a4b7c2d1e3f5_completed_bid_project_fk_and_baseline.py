"""Add completed_bid.project_id UUID FK and baseline checks

Revision ID: a4b7c2d1e3f5
Revises: 1f3c9d8a7b61
Create Date: 2026-02-24 02:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b7c2d1e3f5"
down_revision: str | Sequence[str] | None = "1f3c9d8a7b61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Step 1: Add new UUID column
        op.add_column(
            "completed_bid",
            sa.Column("project_id_new", sa.Uuid(), nullable=True),
        )
        # Step 2: Migrate existing text values to UUID where valid
        op.execute(
            "UPDATE completed_bid SET project_id_new = project_id::uuid "
            "WHERE project_id IS NOT NULL AND project_id ~ "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"
        )
        # Step 3: Drop old column, rename new
        op.drop_column("completed_bid", "project_id")
        op.alter_column("completed_bid", "project_id_new", new_column_name="project_id")
        # Step 4: Add FK constraint
        op.create_foreign_key(
            "fk_completed_bid_project_id",
            "completed_bid",
            "project",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
    else:
        # SQLite: recreate table via batch mode
        with op.batch_alter_table("completed_bid", schema=None) as batch_op:
            batch_op.alter_column(
                "project_id",
                existing_type=sa.Text(),
                type_=sa.Uuid(),
                existing_nullable=True,
                nullable=True,
            )
            batch_op.create_foreign_key(
                "fk_completed_bid_project_id",
                "project",
                ["project_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_constraint("fk_completed_bid_project_id", "completed_bid", type_="foreignkey")
        op.alter_column(
            "completed_bid",
            "project_id",
            existing_type=sa.Uuid(),
            type_=sa.Text(),
            existing_nullable=True,
            postgresql_using="project_id::text",
        )
    else:
        with op.batch_alter_table("completed_bid", schema=None) as batch_op:
            batch_op.drop_constraint("fk_completed_bid_project_id", type_="foreignkey")
            batch_op.alter_column(
                "project_id",
                existing_type=sa.Uuid(),
                type_=sa.Text(),
                existing_nullable=True,
                nullable=True,
            )
