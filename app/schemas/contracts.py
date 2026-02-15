from __future__ import annotations

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


class RenderWordResponse(BaseModel):
    output_path: str


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
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3-pro"
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


class ProjectModelPolicyUpsertRequest(BaseModel):
    extract_profile_id: str | None = None
    generate_profile_id: str | None = None
    review_profile_id: str | None = None
    embed_profile_id: str | None = None
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
    query_rewrite_profile_id: str | None = None
    program_support_profile_id: str | None = None
    enable_review: bool
    token_budget_total: int
    token_budget_used: int
    concurrency_limits: dict


class ExpertLibraryIngestResponse(BaseModel):
    status: str
    expert_doc_id: str
    source_document_id: str | None = None
    filename: str
    page_count: int
    chunk_count: int
    qdrant_upserted: int
    warnings: list[str] = Field(default_factory=list)


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
