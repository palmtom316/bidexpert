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


class HealthResponse(BaseModel):
    status: str
