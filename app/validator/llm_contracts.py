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
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_code_fence(raw: str) -> str:
    return _FENCE.sub("", raw).strip()


def parse_json_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    cleaned = _strip_code_fence(str(raw))
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = _attempt_json_repair(cleaned)
        if repaired is None:
            raise ValueError("llm output is not valid JSON") from exc
        parsed = repaired
    if not isinstance(parsed, dict):
        raise ValueError("llm output JSON must be an object")
    return parsed


def _attempt_json_repair(raw: str) -> dict[str, Any] | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = raw[start : end + 1]
    candidate = _TRAILING_COMMA.sub(r"\1", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_v11_generation_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if "content_blocks" in payload:
        return payload
    if "content" not in payload:
        return None

    content_text = str(payload.get("content") or "").strip() or "NEED_HUMAN_INPUT"
    evidence_items = payload.get("evidence")
    evidence_ids: list[str] = []
    if isinstance(evidence_items, list):
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            chunk_id = str(item.get("chunk_id", "")).strip()
            if chunk_id:
                evidence_ids.append(chunk_id)
    if not evidence_ids:
        evidence_ids = ["NEED_EVIDENCE"]
    return {
        "content_blocks": [
            {
                "type": "paragraph",
                "text": content_text,
                "evidence_ids": evidence_ids,
            }
        ]
    }


def validate_generation_payload(raw: str | dict[str, Any]) -> SectionGenerationPayload:
    payload = parse_json_payload(raw)
    normalized_payload = _normalize_v11_generation_payload(payload) or payload
    try:
        parsed = SectionGenerationPayload.model_validate(normalized_payload)
    except ValidationError as exc:
        raise ValueError("generation payload schema validation failed") from exc
    return parsed


def ensure_generation_evidence_binding(
    payload: SectionGenerationPayload,
    *,
    allowed_evidence_ids: list[str] | None = None,
) -> SectionGenerationPayload:
    if allowed_evidence_ids is None:
        return payload

    allowed = {str(item).strip() for item in allowed_evidence_ids if str(item).strip()}
    invalid: list[str] = []
    for block in payload.content_blocks:
        for evidence_id in block.evidence_ids:
            if evidence_id not in allowed:
                invalid.append(evidence_id)

    if invalid:
        joined = ",".join(sorted(set(invalid)))
        raise ValueError(f"generation payload contains unknown evidence_ids: {joined}")
    return payload


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
