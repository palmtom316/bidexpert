import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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


class WorkflowRun(Base):
    __tablename__ = "workflow_run"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    sections_json: Mapped[dict] = mapped_column(JSON, default=dict)
    section_status_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE")
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    section_anchor: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_json: Mapped[dict | None] = mapped_column(JSON)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Requirement(Base):
    __tablename__ = "requirement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    requirement_code: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[RequirementStrength] = mapped_column(
        Enum(RequirementStrength, name="requirement_strength"), nullable=False
    )
    score_weight: Mapped[float | None] = mapped_column(Numeric(6, 2))
    title: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    location_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id")
    )
    location_page_no: Mapped[int | None] = mapped_column(Integer)
    location_anchor: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    deliverables: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExpertDoc(Base):
    __tablename__ = "expert_doc"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
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
    forbidden_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunk"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expert_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expert_doc.id", ondelete="CASCADE"), nullable=False
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
    forbidden_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    qdrant_point_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComplianceMatrix(Base):
    __tablename__ = "compliance_matrix"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirement.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MatrixStatus] = mapped_column(
        Enum(MatrixStatus, name="matrix_status"), default=MatrixStatus.NOT_FOUND
    )
    planned_section: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationVersion(Base):
    __tablename__ = "generation_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generation_version.id", ondelete="CASCADE"), nullable=False
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section_content.id", ondelete="SET NULL")
    )
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict | None] = mapped_column(JSON)
    requirement_codes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    origin: Mapped[SectionOrigin] = mapped_column(Enum(SectionOrigin, name="section_origin"), default=SectionOrigin.AI)
    edit_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    has_placeholders: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SectionRevision(Base):
    __tablename__ = "section_revision"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    base_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section_content.id", ondelete="CASCADE"), nullable=False
    )
    rev_no: Mapped[int] = mapped_column(Integer, nullable=False)
    editor: Mapped[str] = mapped_column(Text, nullable=False)
    patch_diff: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestJob(Base):
    __tablename__ = "ingest_job"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="SET NULL")
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.PENDING)
    report_json: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderProfile(Base):
    __tablename__ = "provider_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[ProviderScope] = mapped_column(
        Enum(ProviderScope, name="provider_scope"), default=ProviderScope.PROJECT, nullable=False
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectModelPolicy(Base):
    __tablename__ = "project_model_policy"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    extract_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    generate_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    review_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    embed_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    query_rewrite_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    program_support_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
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
            "query_rewrite": 2,
            "program_support": 1,
        },
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompletedBid(Base):
    __tablename__ = "completed_bid"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str | None] = mapped_column(Text)
    project_name: Mapped[str] = mapped_column(Text, nullable=False)
    engineering_category: Mapped[str | None] = mapped_column(Text)
    tenderer: Mapped[str | None] = mapped_column(Text)
    bid_result: Mapped[str] = mapped_column(Text, nullable=False, default="WON")
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_info: Mapped[str | None] = mapped_column(Text)
    completed_date: Mapped[Date | None] = mapped_column(Date)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="SET NULL")
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generation_version.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    provider_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profile.id", ondelete="SET NULL")
    )
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenderKeyInfo(Base):
    __tablename__ = "tender_key_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_analysis_run.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    outline_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoringReport(Base):
    __tablename__ = "scoring_report"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    score_total: Mapped[float] = mapped_column(Numeric(6, 2))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
