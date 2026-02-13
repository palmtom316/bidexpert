from app.db.base import Base
from app.db.session import engine
from app.models import tables  # noqa: F401


def _apply_postgres_runtime_migrations() -> None:
    if engine.dialect.name != "postgresql":
        return

    stmts = [
        "ALTER TABLE project ADD COLUMN IF NOT EXISTS sensitivity sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK';",
        "ALTER TABLE project ADD COLUMN IF NOT EXISTS token_budget_total int NOT NULL DEFAULT 500000;",
        "ALTER TABLE project ADD COLUMN IF NOT EXISTS token_budget_used int NOT NULL DEFAULT 0;",
        "ALTER TABLE evidence_chunk ADD COLUMN IF NOT EXISTS source_locator jsonb;",
        "ALTER TABLE evidence_chunk ADD COLUMN IF NOT EXISTS valid_to date;",
        "ALTER TABLE evidence_chunk ADD COLUMN IF NOT EXISTS sensitivity_level sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK';",
        "ALTER TABLE section_content ADD COLUMN IF NOT EXISTS parent_section_id uuid REFERENCES section_content(id) ON DELETE SET NULL;",
        "ALTER TABLE section_content ADD COLUMN IF NOT EXISTS origin section_origin NOT NULL DEFAULT 'AI';",
        "ALTER TABLE section_content ADD COLUMN IF NOT EXISTS edit_summary text;",
        "ALTER TABLE section_content ADD COLUMN IF NOT EXISTS created_by text;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS budget_remaining int;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS retry_count int NOT NULL DEFAULT 0;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS fallback_count int NOT NULL DEFAULT 0;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS cache_hit boolean NOT NULL DEFAULT false;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS pricing_blocked boolean NOT NULL DEFAULT false;",
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'section_origin') THEN CREATE TYPE section_origin AS ENUM ('AI', 'HUMAN', 'MERGE'); END IF; END $$;")
        for stmt in stmts:
            conn.exec_driver_sql(stmt)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _apply_postgres_runtime_migrations()
