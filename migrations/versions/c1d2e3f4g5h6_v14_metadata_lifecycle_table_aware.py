"""v1.4 metadata, lifecycle, table-aware chunking + kb_ingest_run

Revision ID: c1d2e3f4g5h6
Revises: b5c8d3e6f7a1
Create Date: 2026-02-25 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g5h6"
down_revision: str | Sequence[str] | None = "b5c8d3e6f7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KB_INGEST_STEP_VALUES = (
    "RECEIVED", "PARSE_READY", "METADATA_EXTRACTED",
    "LIFECYCLE_VALIDATED", "TABLE_CHUNKED", "CHUNKED",
    "EMBEDDING_DONE", "UPSERTED", "KB_READY", "FAILED",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── expert_doc: add lifecycle + metadata columns ────────────
    op.add_column("expert_doc", sa.Column("standard_code", sa.Text(), nullable=True))
    op.add_column("expert_doc", sa.Column("version_year", sa.Integer(), nullable=True))
    op.add_column("expert_doc", sa.Column("standard_status", sa.Text(), nullable=False, server_default="active"))
    op.add_column("expert_doc", sa.Column("expiration_date", sa.Date(), nullable=True))
    op.add_column("expert_doc", sa.Column("voltage_level_kv", sa.Integer(), nullable=True))
    op.add_column("expert_doc", sa.Column("project_type", sa.Text(), nullable=True))
    op.add_column("expert_doc", sa.Column("core_equipment", sa.Text(), nullable=True))
    op.add_column("expert_doc", sa.Column("region", sa.Text(), nullable=True))

    # ── evidence_chunk: add lifecycle + metadata + table-aware columns
    op.add_column("evidence_chunk", sa.Column("standard_code", sa.Text(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("standard_status", sa.Text(), nullable=False, server_default="active"))
    op.add_column("evidence_chunk", sa.Column("expiration_date", sa.Date(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("voltage_level_kv", sa.Integer(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("project_type", sa.Text(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("region", sa.Text(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("chunk_kind", sa.Text(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("table_header", sa.Text(), nullable=True))
    op.add_column("evidence_chunk", sa.Column("is_parameter_table", sa.Boolean(), nullable=True))

    # ── Indexes for lifecycle queries ───────────────────────────
    op.create_index("idx_expert_doc_standard_code", "expert_doc", ["standard_code"])
    op.create_index("idx_expert_doc_standard_status", "expert_doc", ["standard_status"])

    # ── kb_ingest_run table ─────────────────────────────────────
    if dialect == "postgresql":
        step_enum = sa.Enum(*_KB_INGEST_STEP_VALUES, name="kb_ingest_step")
        step_enum.create(bind, checkfirst=True)

    op.create_table(
        "kb_ingest_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expert_doc_id", sa.Uuid(), sa.ForeignKey("expert_doc.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column(
            "current_step",
            sa.Enum(*_KB_INGEST_STEP_VALUES, name="kb_ingest_step", create_constraint=True),
            nullable=False,
            server_default="RECEIVED",
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_kb_ingest_run_expert_doc_id", "kb_ingest_run", ["expert_doc_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── Drop kb_ingest_run ──────────────────────────────────────
    op.drop_index("idx_kb_ingest_run_expert_doc_id", table_name="kb_ingest_run")
    op.drop_table("kb_ingest_run")

    if dialect == "postgresql":
        sa.Enum(name="kb_ingest_step").drop(bind, checkfirst=True)

    # ── Drop indexes ────────────────────────────────────────────
    op.drop_index("idx_expert_doc_standard_status", table_name="expert_doc")
    op.drop_index("idx_expert_doc_standard_code", table_name="expert_doc")

    # ── Drop evidence_chunk columns ─────────────────────────────
    op.drop_column("evidence_chunk", "is_parameter_table")
    op.drop_column("evidence_chunk", "table_header")
    op.drop_column("evidence_chunk", "chunk_kind")
    op.drop_column("evidence_chunk", "region")
    op.drop_column("evidence_chunk", "project_type")
    op.drop_column("evidence_chunk", "voltage_level_kv")
    op.drop_column("evidence_chunk", "expiration_date")
    op.drop_column("evidence_chunk", "standard_status")
    op.drop_column("evidence_chunk", "standard_code")

    # ── Drop expert_doc columns ─────────────────────────────────
    op.drop_column("expert_doc", "region")
    op.drop_column("expert_doc", "core_equipment")
    op.drop_column("expert_doc", "project_type")
    op.drop_column("expert_doc", "voltage_level_kv")
    op.drop_column("expert_doc", "expiration_date")
    op.drop_column("expert_doc", "standard_status")
    op.drop_column("expert_doc", "version_year")
    op.drop_column("expert_doc", "standard_code")
