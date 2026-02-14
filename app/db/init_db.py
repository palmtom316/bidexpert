from app.db.base import Base
from app.db.session import engine
from app.models import tables  # noqa: F401


def _apply_postgres_runtime_migrations() -> None:
    if engine.dialect.name != "postgresql":
        return

    stmts = [
        "CREATE TABLE IF NOT EXISTS workflow_run (id text PRIMARY KEY, project_id text NOT NULL, status text NOT NULL, sections_json jsonb NOT NULL DEFAULT '{}'::jsonb, section_status_json jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());",
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
        "CREATE INDEX IF NOT EXISTS idx_expert_doc_industry_created ON expert_doc(industry_tag, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_doc_created ON evidence_chunk(expert_doc_id, created_at DESC);",
        "CREATE TABLE IF NOT EXISTS provider_profile (id uuid PRIMARY KEY, scope provider_scope NOT NULL DEFAULT 'PROJECT', scope_id uuid NOT NULL, provider text NOT NULL, base_url text NULL, default_model text NOT NULL, key_storage key_storage NOT NULL, key_secret_ref text NOT NULL, encrypted_key bytea NULL, allowed_tasks jsonb NOT NULL DEFAULT '[\"*\"]'::jsonb, created_by text NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());",
        "CREATE TABLE IF NOT EXISTS project_model_policy (project_id uuid PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE, generate_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL, review_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL, embed_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL, enable_review boolean NOT NULL DEFAULT true, token_budget_total bigint NOT NULL DEFAULT 500000, token_budget_used bigint NOT NULL DEFAULT 0, concurrency_limits jsonb NOT NULL DEFAULT '{\"generate\":3,\"review\":2,\"embed\":2}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS provider_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL;",
        "ALTER TABLE llm_call_log ADD COLUMN IF NOT EXISTS blocked_reason text;",
        "CREATE TABLE IF NOT EXISTS tender_analysis_run (id uuid PRIMARY KEY, project_id uuid REFERENCES project(id) ON DELETE SET NULL, document_id uuid REFERENCES document(id) ON DELETE SET NULL, filename text NOT NULL, status text NOT NULL, summary_json jsonb NOT NULL DEFAULT '{}'::jsonb, created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());",
        "CREATE TABLE IF NOT EXISTS tender_key_info (id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES tender_analysis_run(id) ON DELETE CASCADE, project_id uuid REFERENCES project(id) ON DELETE SET NULL, document_id uuid REFERENCES document(id) ON DELETE SET NULL, category tender_key_category NOT NULL, title text NULL, content text NOT NULL, page_no int NULL, section_anchor text NULL, score_weight numeric(6,2) NULL, is_must boolean NOT NULL DEFAULT false, importance int NOT NULL DEFAULT 50, source_quote text NULL, created_at timestamptz NOT NULL DEFAULT now());",
        "CREATE INDEX IF NOT EXISTS idx_tender_analysis_project_time ON tender_analysis_run(project_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_tender_key_info_run_category ON tender_key_info(run_id, category);",
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'section_origin') THEN CREATE TYPE section_origin AS ENUM ('AI', 'HUMAN', 'MERGE'); END IF; END $$;")
        conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'provider_scope') THEN CREATE TYPE provider_scope AS ENUM ('PROJECT', 'USER', 'TENANT'); END IF; END $$;")
        conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'key_storage') THEN CREATE TYPE key_storage AS ENUM ('ENCRYPTED_DB', 'TEMP_REDIS', 'VAULT'); END IF; END $$;")
        conn.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tender_key_category') THEN CREATE TYPE tender_key_category AS ENUM ('BIDDING_POINTS', 'SCORING_POINTS', 'COMPLIANCE_REQUIREMENTS', 'BONUS_POINTS', 'RISK_ALERTS'); END IF; END $$;")
        for stmt in stmts:
            conn.exec_driver_sql(stmt)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _apply_postgres_runtime_migrations()
