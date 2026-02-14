CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_kind') THEN
    CREATE TYPE doc_kind AS ENUM ('TENDER', 'CLARIFICATION', 'EXPERT', 'AWARD');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sensitivity_level') THEN
    CREATE TYPE sensitivity_level AS ENUM ('PUBLIC_OK', 'SENSITIVE');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'requirement_strength') THEN
    CREATE TYPE requirement_strength AS ENUM ('MUST', 'SCORE', 'FORMAT', 'OTHER');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'matrix_status') THEN
    CREATE TYPE matrix_status AS ENUM ('SUPPORTED', 'NEED_HUMAN_INPUT', 'NOT_FOUND');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
    CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS project (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL,
  owner_user_id    text NOT NULL,
  description      text,
  industry_tag     text,
  customer_tag     text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_owner ON project(owner_user_id);

CREATE TABLE IF NOT EXISTS document (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         uuid REFERENCES project(id) ON DELETE CASCADE,
  kind              doc_kind NOT NULL,
  filename          text NOT NULL,
  content_type      text,
  object_uri        text NOT NULL,
  sha256            text,
  page_count        int,
  language          text,
  sensitivity       sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK',
  created_by        text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_project ON document(project_id);
CREATE INDEX IF NOT EXISTS idx_document_kind ON document(kind);
CREATE INDEX IF NOT EXISTS idx_document_sha256 ON document(sha256);

CREATE TABLE IF NOT EXISTS doc_block (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id        uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  block_type         text NOT NULL,
  page_no            int,
  section_anchor     text,
  content_text       text,
  content_json       jsonb,
  char_start         int,
  char_end           int,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_block_document ON doc_block(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_block_page ON doc_block(document_id, page_no);
CREATE INDEX IF NOT EXISTS idx_doc_block_anchor ON doc_block(document_id, section_anchor);

CREATE TABLE IF NOT EXISTS requirement (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  requirement_code    text NOT NULL,
  strength            requirement_strength NOT NULL,
  score_weight        numeric(6,2),
  title              text,
  original_text       text NOT NULL,
  location_document_id uuid REFERENCES document(id),
  location_page_no    int,
  location_anchor     text,
  constraints         jsonb,
  deliverables        jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_requirement_code_per_project
  ON requirement(project_id, requirement_code);

CREATE INDEX IF NOT EXISTS idx_requirement_strength ON requirement(project_id, strength);

CREATE TABLE IF NOT EXISTS expert_doc (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id  uuid REFERENCES document(id) ON DELETE SET NULL,
  doc_type            text NOT NULL,
  title               text,
  industry_tag        text,
  section_type        text,
  sensitivity         sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK',
  valid_from          date,
  valid_to            date,
  forbidden_tags      text[] NOT NULL DEFAULT ARRAY[]::text[],
  created_by          text NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expert_doc_type ON expert_doc(doc_type);
CREATE INDEX IF NOT EXISTS idx_expert_doc_sensitivity ON expert_doc(sensitivity);
CREATE INDEX IF NOT EXISTS idx_expert_doc_validity ON expert_doc(valid_to);
CREATE INDEX IF NOT EXISTS idx_expert_doc_industry_created ON expert_doc(industry_tag, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_chunk (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  expert_doc_id       uuid NOT NULL REFERENCES expert_doc(id) ON DELETE CASCADE,
  chunk_no            int NOT NULL,
  excerpt_text        text NOT NULL,
  excerpt_hash        text,
  location            jsonb,
  quality_score       numeric(5,2) NOT NULL DEFAULT 0,
  forbidden_tags      text[] NOT NULL DEFAULT ARRAY[]::text[],
  qdrant_point_id     text,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_no_per_doc
  ON evidence_chunk(expert_doc_id, chunk_no);

CREATE INDEX IF NOT EXISTS idx_evidence_qdrant_point ON evidence_chunk(qdrant_point_id);
CREATE INDEX IF NOT EXISTS idx_evidence_doc_created ON evidence_chunk(expert_doc_id, created_at DESC);

CREATE TABLE IF NOT EXISTS compliance_matrix (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  requirement_id      uuid NOT NULL REFERENCES requirement(id) ON DELETE CASCADE,
  status             matrix_status NOT NULL DEFAULT 'NOT_FOUND',
  planned_section     text,
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  notes              text,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_matrix_per_requirement
  ON compliance_matrix(project_id, requirement_id);

CREATE INDEX IF NOT EXISTS idx_matrix_status ON compliance_matrix(project_id, status);

CREATE TABLE IF NOT EXISTS generation_version (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_no            int NOT NULL,
  status               job_status NOT NULL DEFAULT 'PENDING',
  created_by           text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  model_used           text,
  config               jsonb,
  output_doc_object_uri text
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_version_no_per_project
  ON generation_version(project_id, version_no);

CREATE INDEX IF NOT EXISTS idx_version_status ON generation_version(project_id, status);

CREATE TABLE IF NOT EXISTS section_content (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_id          uuid NOT NULL REFERENCES generation_version(id) ON DELETE CASCADE,
  section_key         text NOT NULL,
  section_title       text NOT NULL,
  content_md          text NOT NULL,
  content_json        jsonb,
  requirement_codes   text[] NOT NULL DEFAULT ARRAY[]::text[],
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  has_placeholders    boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_section_project_version ON section_content(project_id, version_id);
CREATE INDEX IF NOT EXISTS idx_section_key ON section_content(project_id, section_key);

CREATE TABLE IF NOT EXISTS ingest_job (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  source_document_id  uuid REFERENCES document(id) ON DELETE SET NULL,
  status              job_status NOT NULL DEFAULT 'PENDING',
  report_json         jsonb,
  created_by          text NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz
);

CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_job(status);

CREATE TABLE IF NOT EXISTS audit_log (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  actor_user_id       text NOT NULL,
  action              text NOT NULL,
  target_id            text,
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_project_time ON audit_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_log(actor_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_call_log (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  version_id          uuid REFERENCES generation_version(id) ON DELETE SET NULL,
  actor_user_id       text NOT NULL,
  model_name          text NOT NULL,
  purpose             text NOT NULL,
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  prompt_hash         text,
  input_tokens        int,
  output_tokens       int,
  latency_ms          int,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_project_time ON llm_call_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_model_purpose ON llm_call_log(model_name, purpose);

-- v3.2 governance/resilience extensions (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'section_origin') THEN
    CREATE TYPE section_origin AS ENUM ('AI', 'HUMAN', 'MERGE');
  END IF;
END$$;

ALTER TABLE project
  ADD COLUMN IF NOT EXISTS sensitivity sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK',
  ADD COLUMN IF NOT EXISTS token_budget_total int NOT NULL DEFAULT 500000,
  ADD COLUMN IF NOT EXISTS token_budget_used int NOT NULL DEFAULT 0;

ALTER TABLE evidence_chunk
  ADD COLUMN IF NOT EXISTS source_locator jsonb,
  ADD COLUMN IF NOT EXISTS valid_to date,
  ADD COLUMN IF NOT EXISTS sensitivity_level sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK';

ALTER TABLE section_content
  ADD COLUMN IF NOT EXISTS parent_section_id uuid REFERENCES section_content(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS origin section_origin NOT NULL DEFAULT 'AI',
  ADD COLUMN IF NOT EXISTS edit_summary text,
  ADD COLUMN IF NOT EXISTS created_by text;

CREATE TABLE IF NOT EXISTS section_revision (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  base_section_id    uuid NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
  rev_no             int NOT NULL,
  editor             text NOT NULL,
  patch_diff         text NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_section_revision_base ON section_revision(base_section_id, rev_no DESC);

ALTER TABLE llm_call_log
  ADD COLUMN IF NOT EXISTS budget_remaining int,
  ADD COLUMN IF NOT EXISTS retry_count int NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fallback_count int NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cache_hit boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS pricing_blocked boolean NOT NULL DEFAULT false;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'provider_scope') THEN
    CREATE TYPE provider_scope AS ENUM ('PROJECT', 'USER', 'TENANT');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'key_storage') THEN
    CREATE TYPE key_storage AS ENUM ('ENCRYPTED_DB', 'TEMP_REDIS', 'VAULT');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tender_key_category') THEN
    CREATE TYPE tender_key_category AS ENUM (
      'BIDDING_POINTS',
      'SCORING_POINTS',
      'COMPLIANCE_REQUIREMENTS',
      'BONUS_POINTS',
      'RISK_ALERTS'
    );
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS provider_profile (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope              provider_scope NOT NULL DEFAULT 'PROJECT',
  scope_id           uuid NOT NULL,
  provider           text NOT NULL,
  base_url           text,
  default_model      text NOT NULL,
  key_storage        key_storage NOT NULL,
  key_secret_ref     text NOT NULL,
  encrypted_key      bytea,
  allowed_tasks      jsonb NOT NULL DEFAULT '["*"]'::jsonb,
  created_by         text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provider_profile_scope ON provider_profile(scope, scope_id);

CREATE TABLE IF NOT EXISTS project_model_policy (
  project_id         uuid PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
  generate_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL,
  review_profile_id  uuid REFERENCES provider_profile(id) ON DELETE SET NULL,
  embed_profile_id   uuid REFERENCES provider_profile(id) ON DELETE SET NULL,
  enable_review      boolean NOT NULL DEFAULT true,
  token_budget_total bigint NOT NULL DEFAULT 500000,
  token_budget_used  bigint NOT NULL DEFAULT 0,
  concurrency_limits jsonb NOT NULL DEFAULT '{"generate":3,"review":2,"embed":2}'::jsonb,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE llm_call_log
  ADD COLUMN IF NOT EXISTS provider_profile_id uuid REFERENCES provider_profile(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS blocked_reason text;

CREATE TABLE IF NOT EXISTS tender_analysis_run (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         uuid REFERENCES project(id) ON DELETE SET NULL,
  document_id        uuid REFERENCES document(id) ON DELETE SET NULL,
  filename           text NOT NULL,
  status             text NOT NULL,
  summary_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by         text NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tender_analysis_project_time
  ON tender_analysis_run(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tender_key_info (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id             uuid NOT NULL REFERENCES tender_analysis_run(id) ON DELETE CASCADE,
  project_id         uuid REFERENCES project(id) ON DELETE SET NULL,
  document_id        uuid REFERENCES document(id) ON DELETE SET NULL,
  category           tender_key_category NOT NULL,
  title              text,
  content            text NOT NULL,
  page_no            int,
  section_anchor     text,
  score_weight       numeric(6,2),
  is_must            boolean NOT NULL DEFAULT false,
  importance         int NOT NULL DEFAULT 50,
  source_quote       text,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tender_key_info_run_category
  ON tender_key_info(run_id, category);
