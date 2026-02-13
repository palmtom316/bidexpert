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
    missing_sentences: list[str]
    coverage: float
    budget_remaining: int | None = None
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)
    coverage_map: dict[str, list[str]] = Field(default_factory=dict)


class WorkflowSectionRequest(BaseModel):
    project_id: str
    section_key: str
    section_title: str
    requirement_texts: list[str]
    industry_tag: str | None = None


class WorkflowSectionResponse(BaseModel):
    section_key: str
    status: str
    task_ids: dict[str, str]


class HealthResponse(BaseModel):
    status: str
