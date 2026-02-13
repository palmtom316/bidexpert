from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.contracts import (
    GateValidationRequest,
    GateValidationResponse,
    HealthResponse,
    ParseTenderRequest,
    ParseTenderResponse,
    PricingFuseRequest,
    PricingFuseResponse,
    RenderWordRequest,
    RenderWordResponse,
)
from app.services.evidence_validator import run_three_gates
from app.services.pricing_guard import detect_pricing_content
from app.services.tender_parser import parse_tender_requirements
from app.services.word_renderer import render_word

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/v1/tender/parse", response_model=ParseTenderResponse)
def parse_tender(payload: ParseTenderRequest) -> ParseTenderResponse:
    blocked, reasons = detect_pricing_content(payload.text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    parsed = parse_tender_requirements(payload.text)
    return ParseTenderResponse(requirements=parsed.requirements, status=parsed.status)


@router.post("/v1/policy/pricing-fuse", response_model=PricingFuseResponse)
def pricing_fuse(payload: PricingFuseRequest) -> PricingFuseResponse:
    blocked, reasons = detect_pricing_content(payload.text)
    return PricingFuseResponse(blocked=blocked, reasons=reasons)


@router.post("/v1/generation/validate", response_model=GateValidationResponse)
def validate_generation(payload: GateValidationRequest) -> GateValidationResponse:
    evidence_map = {item.evidence_id: item.text for item in payload.evidence}
    evidence_texts = [evidence_map[eid] for eid in payload.evidence_ids if eid in evidence_map]
    result = run_three_gates(
        generated_text=payload.generated_text,
        evidence_ids=payload.evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=1,
        requirement_total=1,
        coverage_threshold=settings.min_matrix_coverage,
    )
    return GateValidationResponse(
        status=result.status,
        missing_sentences=result.missing_sentences,
        coverage=result.coverage,
    )


@router.post("/v1/render/word", response_model=RenderWordResponse)
def render_doc(payload: RenderWordRequest) -> RenderWordResponse:
    output = render_word(
        output_path=payload.output_path,
        placeholders=payload.placeholders,
        template_path=payload.template_path,
    )
    return RenderWordResponse(output_path=output)
