from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ParseTenderRequest(BaseModel):
    text: str = Field(min_length=1)


class ParsedRequirement(BaseModel):
    requirement_id: str
    original_text: str
    page_no: int | None = None
    section_anchor: str | None = None
    is_must: bool = False
    score_weight: float | None = None
    format_constraints: dict = Field(default_factory=dict)


class ParseTenderResponse(BaseModel):
    requirements: list[ParsedRequirement]
    status: str


class PricingFuseRequest(BaseModel):
    text: str


class PricingFuseResponse(BaseModel):
    blocked: bool
    reasons: list[str]


class SanitizeRequest(BaseModel):
    text: str
    strategy: str = "mask"
    allowlist: list[str] = Field(default_factory=list)


class SanitizeResponse(BaseModel):
    blocked: bool
    warnings: list[str]
    sanitized_text: str


class EvidenceItem(BaseModel):
    evidence_id: str
    text: str


class GateValidationRequest(BaseModel):
    requirement_id: str
    generated_text: str
    evidence_ids: list[str]
    evidence: list[EvidenceItem]


class GateValidationResponse(BaseModel):
    status: str
    missing_sentences: list[str]
    coverage: float


class RenderWordRequest(BaseModel):
    output_path: str
    placeholders: dict[str, str]
    template_path: str | None = None
    style_config: dict | None = None


class RenderWordResponse(BaseModel):
    output_path: str


class EvidencePageRange(BaseModel):
    start_page: int = Field(ge=0)
    end_page: int = Field(ge=0)


class EvidenceReference(BaseModel):
    doc_id: str
    page_range: EvidencePageRange
    chunk_id: str


class WordHeadingBlock(BaseModel):
    type: Literal["heading"]
    style: Literal["Title1", "Title2", "Title3", "Title4"]
    text: str = Field(min_length=1)


class WordParagraphBlock(BaseModel):
    type: Literal["paragraph"]
    style: Literal["BodyText", "BodyText_Indent", "ClauseText"]
    text: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    risk_level: Literal["high", "medium", "low"] | None = None


class WordTableBlock(BaseModel):
    type: Literal["table"]
    table_data: list[dict[str, str]] = Field(min_length=1)


class WordImageMetaBlock(BaseModel):
    type: Literal["image_meta"]
    name: str = Field(min_length=1)
    caption: str = Field(min_length=1)
    file_ref: str = Field(min_length=1)


class WordAttachmentMetaBlock(BaseModel):
    type: Literal["attachment_meta"]
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    file_ref: str = Field(min_length=1)


WordContentBlock = Annotated[
    WordHeadingBlock | WordParagraphBlock | WordTableBlock | WordImageMetaBlock | WordAttachmentMetaBlock,
    Field(discriminator="type"),
]


class WordStructuredContent(BaseModel):
    body: list[WordContentBlock] = Field(default_factory=list)
    appendix: list[WordContentBlock] = Field(default_factory=list)


class RenderWordStructuredRequest(BaseModel):
    output_path: str
    placeholders: dict[str, str] = Field(default_factory=dict)
    content: WordStructuredContent
    template_path: str | None = None
    style_config: dict | None = None
    export_pdf: bool = False


class RenderWordStructuredResponse(BaseModel):
    output_path: str
    pdf_path: str | None = None


class DocBlockItem(BaseModel):
    page_no: int
    block_type: str
    section_anchor: str | None = None
    content_text: str
    char_start: int
    char_end: int


class IngestUploadResponse(BaseModel):
    status: str
    filename: str
    page_count: int
    blocks: list[DocBlockItem]
    requirements: list[ParsedRequirement]


class EnqueueIngestResponse(BaseModel):
    task_id: str
    status: str


class BatchIngestDirectoryRequest(BaseModel):
    directory: str = Field(min_length=1)


class BatchIngestDirectoryResponse(BaseModel):
    status: str
    total_files: int
    task_ids: list[str]


class SectionFeedbackUpsertRequest(BaseModel):
    outline_id: str
    section_key: str
    section_title: str
    expert_doc_id: str
    content_md: str = Field(min_length=1)
    industry_tag: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None


class EvidenceUpsertItem(BaseModel):
    chunk_id: str
    text: str
    doc_type: str = "EXPERT"
    section_type: str | None = None
    industry_tag: str | None = None
    sensitivity_level: str = "PUBLIC_OK"
    valid_to: str | None = None
    forbidden_tags: list[str] = Field(default_factory=list)
    quality_score: float = 80.0
    source_locator: dict | None = None
    parent_chunk_id: str | None = None
    anchor_type: Literal["clause", "table", "paragraph"] | None = None


class EvidenceUpsertRequest(BaseModel):
    expert_doc_id: str
    chunks: list[EvidenceUpsertItem]


class EvidenceSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    industry_tag: str | None = None


class EvidenceSearchHit(BaseModel):
    chunk_id: str
    score: float
    text: str
    payload: dict


class EvidenceSearchResponse(BaseModel):
    hits: list[EvidenceSearchHit]


class HistoricalExtractRequest(BaseModel):
    expert_doc_id: str
    text: str = Field(min_length=1)
    industry_tag: str | None = None
    model_id: str | None = None


class DraftGenerationRequest(BaseModel):
    requirement_id: str
    requirement_text: str
    top_k: int = 5
    project_id: str | None = None
    industry_tag: str | None = None
    tender_template_id: str | None = None


class DraftGenerationResponse(BaseModel):
    generated_text: str
    evidence_ids: list[str]
    status: str
    llm_provider: str = "qwen"
    llm_model: str = "qwen3.5"
    missing_sentences: list[str]
    coverage: float
    budget_remaining: int | None = None
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)
    coverage_map: dict[str, list[str]] = Field(default_factory=dict)
    retrieval_log: list[dict] = Field(default_factory=list)
    generation_json: dict = Field(default_factory=dict)
    review_json: dict | None = None


class WorkflowSectionRequest(BaseModel):
    outline_id: str
    project_id: str
    section_key: str
    section_title: str
    requirement_texts: list[str]
    industry_tag: str | None = None


class WorkflowSectionResponse(BaseModel):
    section_key: str
    status: str
    task_ids: dict[str, str]


class SectionConfirmRequest(BaseModel):
    outline_id: str
    section_key: str
    approved: bool


class SectionConfirmResponse(BaseModel):
    outline_id: str
    section_key: str
    status: str


class OutlineSection(BaseModel):
    section_key: str
    section_title: str
    requirement_texts: list[str] = Field(default_factory=list)


class OutlineCreateRequest(BaseModel):
    project_id: str
    tender_text: str = Field(min_length=1)


class OutlineCreateResponse(BaseModel):
    outline_id: str
    project_id: str
    status: str
    sections: list[OutlineSection]


class OutlineConfirmRequest(BaseModel):
    outline_id: str
    approved: bool


class OutlineConfirmResponse(BaseModel):
    outline_id: str
    status: str


class HealthResponse(BaseModel):
    status: str


class ProviderProfileCreateRequest(BaseModel):
    project_id: str
    provider: str = Field(min_length=1)
    base_url: str | None = None
    default_model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    key_storage: str = "ENCRYPTED_DB"
    allowed_tasks: list[str] = Field(default_factory=lambda: ["*"])


class ProviderProfileItem(BaseModel):
    id: str
    scope: str
    scope_id: str
    provider: str
    base_url: str | None = None
    default_model: str
    key_storage: str
    key_secret_ref: str
    allowed_tasks: list[str]
    created_by: str | None = None


class ProviderProfileListResponse(BaseModel):
    items: list[ProviderProfileItem]


class ProviderProfileCreateResponse(BaseModel):
    profile_id: str
    key_storage: str


class ProviderProfileDeleteResponse(BaseModel):
    profile_id: str
    deleted: bool


class ProviderProfileTestResponse(BaseModel):
    profile_id: str
    ok: bool
    provider: str
    model: str
    detail: str


class ProviderConnectionTestRequest(BaseModel):
    provider: str = Field(min_length=1)
    base_url: str | None = None
    default_model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class ProviderConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    detail: str


class OCRConnectionTestRequest(BaseModel):
    provider: str = Field(min_length=1)
    base_url: str | None = None
    model: str | None = None
    api_key: str = Field(min_length=1)


class OCRConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    detail: str


class ProviderProfileQualifyCase(BaseModel):
    case_id: str
    name: str
    weight: float
    passed: bool
    detail: str


class ProviderProfileQualifyResponse(BaseModel):
    profile_id: str
    provider: str
    model: str
    ready_for_online: bool
    threshold: float
    quality_score: float
    capability_score: float
    model_quality: dict
    cases: list[ProviderProfileQualifyCase]


class ProjectModelPolicyUpsertRequest(BaseModel):
    extract_profile_id: str | None = None
    generate_profile_id: str | None = None
    review_profile_id: str | None = None
    embed_profile_id: str | None = None
    rerank_profile_id: str | None = None
    query_rewrite_profile_id: str | None = None
    program_support_profile_id: str | None = None
    enable_review: bool = True
    token_budget_total: int | None = None
    concurrency_limits: dict | None = None


class ProjectModelPolicyResponse(BaseModel):
    project_id: str
    extract_profile_id: str | None = None
    generate_profile_id: str | None = None
    review_profile_id: str | None = None
    embed_profile_id: str | None = None
    rerank_profile_id: str | None = None
    query_rewrite_profile_id: str | None = None
    program_support_profile_id: str | None = None
    enable_review: bool
    token_budget_total: int
    token_budget_used: int
    concurrency_limits: dict


class CompletedBidCreateRequest(BaseModel):
    project_id: str | None = None
    project_name: str = Field(min_length=1)
    engineering_category: str | None = None
    tenderer: str | None = None
    bid_result: str = "WON"
    file_name: str = Field(min_length=1)
    file_info: str | None = None
    completed_date: str | None = None
    created_by: str | None = "system"


class CompletedBidItem(BaseModel):
    id: str
    project_id: str | None = None
    project_name: str
    engineering_category: str | None = None
    tenderer: str | None = None
    bid_result: str
    file_name: str
    file_info: str | None = None
    completed_date: str | None = None
    created_by: str | None = None
    created_at: str


class CompletedBidListResponse(BaseModel):
    items: list[CompletedBidItem]


class CompletedBidDeleteResponse(BaseModel):
    record_id: str
    deleted: bool


class AuditLogItem(BaseModel):
    id: str
    project_id: str | None = None
    actor_user_id: str
    action: str
    target_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]


class ExpertLibraryIngestResponse(BaseModel):
    status: str
    expert_doc_id: str
    source_document_id: str | None = None
    filename: str
    page_count: int
    chunk_count: int
    qdrant_upserted: int
    warnings: list[str] = Field(default_factory=list)


class ExpertLibraryConvertResponse(BaseModel):
    status: str
    conversion_id: str
    filename: str
    page_count: int
    block_count: int
    section_count: int
    chunk_count: int
    preview_sections: list[str] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ExpertLibraryConvertConfirmRequest(BaseModel):
    conversion_id: str = Field(min_length=1)
    project_id: str | None = None
    industry_tag: str | None = None
    title: str | None = None
    created_by: str = "system"
    doc_type: str = "EXPERT_HISTORY"
    model_id: str | None = None


class ExpertLibraryBatchIngestItem(BaseModel):
    filename: str
    status: str
    expert_doc_id: str | None = None
    source_document_id: str | None = None
    page_count: int = 0
    chunk_count: int = 0
    qdrant_upserted: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ExpertLibraryBatchIngestResponse(BaseModel):
    status: str
    total_files: int
    success_count: int
    failure_count: int
    items: list[ExpertLibraryBatchIngestItem]


class ExpertLibraryDocItem(BaseModel):
    expert_doc_id: str
    title: str | None = None
    industry_tag: str | None = None
    doc_type: str
    created_at: str
    chunk_count: int


class ExpertLibraryDocListResponse(BaseModel):
    items: list[ExpertLibraryDocItem]


class ExpertLibraryChunkItem(BaseModel):
    chunk_id: str
    excerpt_text: str
    section_anchor: str | None = None
    quality_score: float
    valid_to: str | None = None
    created_at: str


class ExpertLibraryChunkListResponse(BaseModel):
    expert_doc_id: str
    items: list[ExpertLibraryChunkItem]


class ExpertLibraryStructuredIngestRequest(BaseModel):
    project_id: str | None = None
    industry_tag: str | None = None
    created_by: str = "system"
    standard_items: list[str] = Field(default_factory=list)
    company_performance_items: list[str] = Field(default_factory=list)
    company_qualification_items: list[str] = Field(default_factory=list)
    pm_qualification_performance_items: list[str] = Field(default_factory=list)
    safety_production_items: list[str] = Field(default_factory=list)
    quality_management_items: list[str] = Field(default_factory=list)
    environmental_protection_items: list[str] = Field(default_factory=list)
    construction_method_items: list[str] = Field(default_factory=list)
    equipment_material_items: list[str] = Field(default_factory=list)
    financial_credit_items: list[str] = Field(default_factory=list)


class ExpertLibraryStructuredIngestItem(BaseModel):
    category: str
    expert_doc_id: str
    title: str
    chunk_count: int
    qdrant_upserted: int
    warnings: list[str] = Field(default_factory=list)


class ExpertLibraryStructuredIngestResponse(BaseModel):
    status: str
    total_docs: int
    total_chunks: int
    items: list[ExpertLibraryStructuredIngestItem]


class TenderKeyInfoItem(BaseModel):
    id: str
    category: str
    title: str | None = None
    content: str
    page_no: int | None = None
    section_anchor: str | None = None
    score_weight: float | None = None
    is_must: bool = False
    importance: int = 50


class TenderAnalysisSummary(BaseModel):
    total_items: int
    category_counts: dict[str, int]
    key_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TenderAnalyzeUploadResponse(BaseModel):
    run_id: str
    project_id: str | None = None
    document_id: str | None = None
    filename: str
    status: str
    summary: TenderAnalysisSummary


class TenderAnalysisRunItem(BaseModel):
    run_id: str
    project_id: str | None = None
    document_id: str | None = None
    filename: str
    status: str
    created_at: str


class TenderAnalysisRunListResponse(BaseModel):
    items: list[TenderAnalysisRunItem]


class TenderAnalysisDetailResponse(BaseModel):
    run: TenderAnalysisRunItem
    summary: TenderAnalysisSummary
    key_infos: list[TenderKeyInfoItem]


class ReviewSectionRequest(BaseModel):
    project_id: str
    section_key: str
    outline_id: str | None = None


class ReviewFullRequest(BaseModel):
    project_id: str
    outline_id: str | None = None
    enable_ensemble: bool = False
    ensemble_size: int | None = None


class ReviewReportResponse(BaseModel):
    id: str
    project_id: str
    section_key: str
    status: str
    report_json: dict
    created_at: str


class ScoringRequest(BaseModel):
    project_id: str


class ScoringReportResponse(BaseModel):
    id: str
    project_id: str
    score_total: float
    details_json: dict
    created_at: str
