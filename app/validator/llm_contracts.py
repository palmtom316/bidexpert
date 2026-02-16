from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class GenerationContentBlock(BaseModel):
    type: str = Field(default="paragraph", min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class SectionGenerationPayload(BaseModel):
    content_blocks: list[GenerationContentBlock] = Field(min_length=1)


class ReviewAnalysisPayload(BaseModel):
    missing_requirements: list[str] = Field(default_factory=list)
    logical_inconsistencies: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    coverage_estimate: float = Field(ge=0.0, le=1.0)
    score_estimate: float = Field(ge=0.0, le=100.0)
    approved: bool = True
    issues: list[str] = Field(default_factory=list)



class ComplianceIssue(BaseModel):
    requirement_code: str
    issue_type: str = "NON_COMPLIANT"
    description: str
    location_snippet: str | None = None


class ComplianceReviewPayload(BaseModel):
    status: str = Field(pattern="^(PASS|FAIL|WARN)$")
    modeled_issues: list[ComplianceIssue] = Field(default_factory=list)
    general_comments: str | None = None


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_code_fence(raw: str) -> str:
    return _FENCE.sub("", raw).strip()


def parse_json_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = _strip_code_fence(str(raw))
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("llm output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("llm output JSON must be an object")
    return parsed


def validate_generation_payload(raw: str | dict[str, Any]) -> SectionGenerationPayload:
    payload = parse_json_payload(raw)
    try:
        return SectionGenerationPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("generation payload schema validation failed") from exc


def validate_review_payload(raw: str | dict[str, Any]) -> ReviewAnalysisPayload:
    payload = parse_json_payload(raw)
    try:
        return ReviewAnalysisPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("review payload schema validation failed") from exc


def validate_compliance_payload(raw: str | dict[str, Any]) -> ComplianceReviewPayload:
    payload = parse_json_payload(raw)
    try:
        return ComplianceReviewPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("compliance payload schema validation failed") from exc


def build_generation_payload(text: str, evidence_ids: list[str]) -> SectionGenerationPayload:
    return SectionGenerationPayload(
        content_blocks=[
            GenerationContentBlock(
                type="paragraph",
                text=(text or "").strip() or "NEED_HUMAN_INPUT",
                evidence_ids=list(evidence_ids),
            )
        ]
    )


def flatten_generation_payload(payload: SectionGenerationPayload) -> str:
    return "\n".join(block.text for block in payload.content_blocks if block.text.strip()).strip()

