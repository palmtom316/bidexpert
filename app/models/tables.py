import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID, JSONDictType, StringListType, UUIDListType


def utcnow() -> datetime:
    return datetime.now(UTC)


class DocKind(str, enum.Enum):
    TENDER = "TENDER"
    CLARIFICATION = "CLARIFICATION"
    EXPERT = "EXPERT"
    AWARD = "AWARD"


class SensitivityLevel(str, enum.Enum):
    PUBLIC_OK = "PUBLIC_OK"
    SENSITIVE = "SENSITIVE"


class RequirementStrength(str, enum.Enum):
    MUST = "MUST"
    SCORE = "SCORE"
    FORMAT = "FORMAT"
    OTHER = "OTHER"


class MatrixStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    NEED_HUMAN_INPUT = "NEED_HUMAN_INPUT"
    NOT_FOUND = "NOT_FOUND"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SectionOrigin(str, enum.Enum):
    AI = "AI"
    HUMAN = "HUMAN"
    MERGE = "MERGE"


class ProviderScope(str, enum.Enum):
    PROJECT = "PROJECT"
    USER = "USER"
    TENANT = "TENANT"


class KeyStorage(str, enum.Enum):
    ENCRYPTED_DB = "ENCRYPTED_DB"
    TEMP_REDIS = "TEMP_REDIS"
    VAULT = "VAULT"


class TenderKeyCategory(str, enum.Enum):
    BIDDING_POINTS = "BIDDING_POINTS"
    SCORING_POINTS = "SCORING_POINTS"
    COMPLIANCE_REQUIREMENTS = "COMPLIANCE_REQUIREMENTS"
    BONUS_POINTS = "BONUS_POINTS"
    RISK_ALERTS = "RISK_ALERTS"


class KBIngestStep(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PARSE_READY = "PARSE_READY"
    METADATA_EXTRACTED = "METADATA_EXTRACTED"
    LIFECYCLE_VALIDATED = "LIFECYCLE_VALIDATED"
    TABLE_CHUNKED = "TABLE_CHUNKED"
    CHUNKED = "CHUNKED"
    EMBEDDING_DONE = "EMBEDDING_DONE"
    UPSERTED = "UPSERTED"
    KB_READY = "KB_READY"
    FAILED = "FAILED"


class TenderRunStep(str, enum.Enum):
    RECEIVED = "RECEIVED"
    UNPACKED = "UNPACKED"
    VALIDATED = "VALIDATED"
    SECTIONIZED = "SECTIONIZED"
    PRELIM_EXTRACTED = "PRELIM_EXTRACTED"
    FATAL_GATE_CHECKED = "FATAL_GATE_CHECKED"
    SCORING_EXTRACTED = "SCORING_EXTRACTED"
    TECH_EXTRACTED = "TECH_EXTRACTED"
    DEVIATION_BUILT = "DEVIATION_BUILT"
    FORMAT_SIGNATURE_EXTRACTED = "FORMAT_SIGNATURE_EXTRACTED"
    BLUEPRINT_BUILT = "BLUEPRINT_BUILT"
    READY_FOR_WRITING = "READY_FOR_WRITING"
    FATAL_BLOCKED = "FATAL_BLOCKED"
    FAILED = "FAILED"


class WorkflowRun(Base):
    __tablename__ = "workflow_run"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    sections_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    section_status_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    current_step: Mapped[str] = mapped_column(Text, default="G0")
    step_status: Mapped[str] = mapped_column(Text, default="paused")
    resume_from_step: Mapped[str] = mapped_column(Text, default="G1")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industry_tag: Mapped[str | None] = mapped_column(Text)
    customer_tag: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[SensitivityLevel] = mapped_column(
        Enum(SensitivityLevel, name="sensitivity_level"), default=SensitivityLevel.PUBLIC_OK
    )
    token_budget_total: Mapped[int] = mapped_column(Integer, default=500000)
    token_budget_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE")
    )
    kind: Mapped[DocKind] = mapped_column(Enum(DocKind, name="doc_kind"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text)
    object_uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[SensitivityLevel] = mapped_column(
        Enum(SensitivityLevel, name="sensitivity_level"), default=SensitivityLevel.PUBLIC_OK
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocBlock(Base):
    __tablename__ = "doc_block"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    section_anchor: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_json: Mapped[dict | None] = mapped_column(JSONDictType())
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Requirement(Base):
    __tablename__ = "requirement"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    requirement_code: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[RequirementStrength] = mapped_column(
        Enum(RequirementStrength, name="requirement_strength"), nullable=False
    )
    score_weight: Mapped[float | None] = mapped_column(Numeric(6, 2))
    title: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    location_document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document.id")
    )
    location_page_no: Mapped[int | None] = mapped_column(Integer)
    location_anchor: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    deliverables: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExpertDoc(Base):
    __tablename__ = "expert_doc"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document.id", ondelete="SET NULL")
    )
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    industry_tag: Mapped[str | None] = mapped_column(Text)
    section_type: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[SensitivityLevel] = mapped_column(
        Enum(SensitivityLevel, name="sensitivity_level"), default=SensitivityLevel.PUBLIC_OK
    )
    valid_from: Mapped[Date | None] = mapped_column(Date)
    valid_to: Mapped[Date | None] = mapped_column(Date)
    forbidden_tags: Mapped[list[str]] = mapped_column(StringListType(), default=list)
    # v1.4 — Lifecycle red-line fields
    standard_code: Mapped[str | None] = mapped_column(Text)
    version_year: Mapped[int | None] = mapped_column(Integer)
    standard_status: Mapped[str] = mapped_column(Text, default="active")
    expiration_date: Mapped[Date | None] = mapped_column(Date)
    # v1.4 — Metadata auto-tagging fields
    voltage_level_kv: Mapped[int | None] = mapped_column(Integer)
    project_type: Mapped[str | None] = mapped_column(Text)
    core_equipment: Mapped[list[str]] = mapped_column(StringListType(), default=list)
    region: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunk"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    expert_doc_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("expert_doc.id", ondelete="CASCADE"), nullable=False
    )
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_hash: Mapped[str | None] = mapped_column(Text)
    location: Mapped[dict | None] = mapped_column(JSON)
    source_locator: Mapped[dict | None] = mapped_column(JSON)
    valid_to: Mapped[Date | None] = mapped_column(Date)
    sensitivity_level: Mapped[SensitivityLevel] = mapped_column(
        Enum(SensitivityLevel, name="sensitivity_level"), default=SensitivityLevel.PUBLIC_OK
    )
    quality_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    forbidden_tags: Mapped[list[str]] = mapped_column(StringListType(), default=list)
    qdrant_point_id: Mapped[str | None] = mapped_column(Text)
    parent_chunk_id: Mapped[str | None] = mapped_column(Text)
    anchor_type: Mapped[str | None] = mapped_column(Text)
    # v1.4 — Lifecycle red-line fields
    standard_code: Mapped[str | None] = mapped_column(Text)
    standard_status: Mapped[str] = mapped_column(Text, default="active")
    expiration_date: Mapped[Date | None] = mapped_column(Date)
    # v1.4 — Metadata auto-tagging fields
    voltage_level_kv: Mapped[int | None] = mapped_column(Integer)
    project_type: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    # v1.4 — Table-aware chunking fields
    chunk_kind: Mapped[str | None] = mapped_column(Text)
    table_header: Mapped[list[str]] = mapped_column(StringListType(), default=list)
    is_parameter_table: Mapped[bool | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComplianceMatrix(Base):
    __tablename__ = "compliance_matrix"
    __table_args__ = (Index("idx_compliance_matrix_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("requirement.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MatrixStatus] = mapped_column(
        Enum(MatrixStatus, name="matrix_status"), default=MatrixStatus.NOT_FOUND
    )
    planned_section: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDListType(), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GenerationVersion(Base):
    __tablename__ = "generation_version"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.PENDING)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_used: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict | None] = mapped_column(JSON)
    output_doc_object_uri: Mapped[str | None] = mapped_column(Text)


class SectionContent(Base):
    __tablename__ = "section_content"
    __table_args__ = (Index("idx_section_content_project_section_key", "project_id", "section_key"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("generation_version.id", ondelete="CASCADE"), nullable=False
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("section_content.id", ondelete="SET NULL")
    )
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict | None] = mapped_column(JSONDictType())
    requirement_codes: Mapped[list[str]] = mapped_column(StringListType(), default=list)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDListType(), default=list)
    origin: Mapped[SectionOrigin] = mapped_column(Enum(SectionOrigin, name="section_origin"), default=SectionOrigin.AI)
    edit_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    has_placeholders: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SectionRevision(Base):
    __tablename__ = "section_revision"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    base_section_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("section_content.id", ondelete="CASCADE"), nullable=False
    )
    rev_no: Mapped[int] = mapped_column(Integer, nullable=False)
    editor: Mapped[str] = mapped_column(Text, nullable=False)
    patch_diff: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestJob(Base):
    __tablename__ = "ingest_job"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document.id", ondelete="SET NULL")
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.PENDING)
    report_json: Mapped[dict | None] = mapped_column(JSONDictType())
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_project_created_at", "project_id", "created_at"),
        Index("idx_audit_log_action_created_at", "action", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderProfile(Base):
    __tablename__ = "provider_profile"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scope: Mapped[ProviderScope] = mapped_column(
        Enum(ProviderScope, name="provider_scope"), default=ProviderScope.PROJECT, nullable=False
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    default_model: Mapped[str] = mapped_column(Text, nullable=False)
    key_storage: Mapped[KeyStorage] = mapped_column(
        Enum(KeyStorage, name="key_storage"), default=KeyStorage.ENCRYPTED_DB, nullable=False
    )
    key_secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    allowed_tasks: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["*"])
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectModelPolicy(Base):
    __tablename__ = "project_model_policy"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    extract_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    generate_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    review_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    embed_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    rerank_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    query_rewrite_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    program_support_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    enable_review: Mapped[bool] = mapped_column(default=True)
    token_budget_total: Mapped[int] = mapped_column(Integer, default=500000)
    token_budget_used: Mapped[int] = mapped_column(Integer, default=0)
    concurrency_limits: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "extract": 2,
            "generate": 3,
            "review": 2,
            "embed": 2,
            "rerank": 2,
            "query_rewrite": 2,
            "program_support": 1,
        },
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CompletedBid(Base):
    __tablename__ = "completed_bid"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    engineering_category: Mapped[str | None] = mapped_column(Text)
    tenderer: Mapped[str | None] = mapped_column(Text)
    bid_result: Mapped[str] = mapped_column(Text, nullable=False, default="WON")
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_info: Mapped[str | None] = mapped_column(Text)
    completed_date: Mapped[Date | None] = mapped_column(Date)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"
    __table_args__ = (Index("idx_llm_call_log_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("generation_version.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    provider_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(UUIDListType(), default=list)
    prompt_hash: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    budget_remaining: Mapped[int | None] = mapped_column(Integer)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    pricing_blocked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenderAnalysisRun(Base):
    __tablename__ = "tender_analysis_run"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TenderKeyInfo(Base):
    __tablename__ = "tender_key_info"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tender_analysis_run.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document.id", ondelete="SET NULL")
    )
    category: Mapped[TenderKeyCategory] = mapped_column(
        Enum(TenderKeyCategory, name="tender_key_category"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    section_anchor: Mapped[str | None] = mapped_column(Text)
    score_weight: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_must: Mapped[bool] = mapped_column(default=False)
    importance: Mapped[int] = mapped_column(Integer, default=50)
    source_quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewReport(Base):
    __tablename__ = "review_report"
    __table_args__ = (Index("idx_review_report_project_section", "project_id", "section_key"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    outline_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoringReport(Base):
    __tablename__ = "scoring_report"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    score_total: Mapped[float] = mapped_column(Numeric(6, 2))
    details_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenderImportRun(Base):
    __tablename__ = "tender_import_run"
    __table_args__ = (
        Index("idx_tender_import_run_project_id", "project_id"),
        Index("idx_tender_import_run_project_created_at", "project_id", "created_at"),
        Index("idx_tender_import_run_tender_created_at", "tender_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    tender_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    current_step: Mapped[TenderRunStep] = mapped_column(
        Enum(TenderRunStep, name="tender_run_step"), default=TenderRunStep.RECEIVED
    )
    fatal_blocked_reason: Mapped[dict | None] = mapped_column(JSONDictType())
    error_detail: Mapped[str | None] = mapped_column(Text)
    global_facts: Mapped[dict | None] = mapped_column(JSONDictType())
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KBIngestRun(Base):
    __tablename__ = "kb_ingest_run"
    __table_args__ = (
        Index("idx_kb_ingest_run_expert_doc_id", "expert_doc_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    expert_doc_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("expert_doc.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    current_step: Mapped[KBIngestStep] = mapped_column(
        Enum(KBIngestStep, name="kb_ingest_step"), default=KBIngestStep.RECEIVED
    )
    metadata_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TenderAddendum(Base):
    __tablename__ = "tender_addendum"
    __table_args__ = (Index("idx_tender_addendum_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    tender_id: Mapped[str | None] = mapped_column(Text)
    addendum_code: Mapped[str | None] = mapped_column(Text)
    parsed_overrides_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MandatoryClause(Base):
    __tablename__ = "mandatory_clause"
    __table_args__ = (Index("idx_mandatory_clause_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    clause_code: Mapped[str | None] = mapped_column(Text)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BidAssetPool(Base):
    __tablename__ = "bid_asset_pool"
    __table_args__ = (Index("idx_bid_asset_pool_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    asset_name: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_role: Mapped[str] = mapped_column(Text, nullable=False, default="owner")
    metadata_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChapterEvidenceLink(Base):
    __tablename__ = "chapter_evidence_link"
    __table_args__ = (
        Index("idx_chapter_evidence_link_project_id", "project_id"),
        Index("idx_chapter_evidence_link_chapter_key", "chapter_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    chapter_key: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evidence_chunk.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationRun(Base):
    __tablename__ = "generation_run"
    __table_args__ = (
        Index("idx_generation_run_project_id", "project_id"),
        Index("idx_generation_run_project_created_at", "project_id", "created_at"),
        Index("idx_generation_run_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    current_step: Mapped[str] = mapped_column(Text, default="RECEIVED")
    step_status: Mapped[str] = mapped_column(Text, default="paused")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    resume_from_step: Mapped[str] = mapped_column(Text, default="RECEIVED")
    input_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSONDictType())
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScoreEvaluation(Base):
    __tablename__ = "score_evaluation"
    __table_args__ = (
        Index("idx_score_evaluation_generation_run_id", "generation_run_id"),
        Index("idx_score_evaluation_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("generation_run.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    score_total: Mapped[float | None] = mapped_column(Numeric(6, 2))
    details_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComplianceReport(Base):
    __tablename__ = "compliance_report"
    __table_args__ = (
        Index("idx_compliance_report_generation_run_id", "generation_run_id"),
        Index("idx_compliance_report_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("generation_run.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    report_json: Mapped[dict] = mapped_column(JSONDictType(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
