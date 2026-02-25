"""Pydantic models for all v1.1 tender-derived JSON artefacts."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── manifest.json inside .tender.zip ──────────────────────────

class TenderManifest(BaseModel):
    tender_id: str = Field(min_length=1)
    tender_name: str | None = None
    project_type: str | None = None
    voltage_level: str | None = None
    region: str | None = None
    source_tool: str | None = None
    files: dict[str, str] = Field(default_factory=dict)


# ── tender_sections.json ──────────────────────────────────────

class TenderSection(BaseModel):
    section_id: str
    anchor: str
    title: str
    content: str
    page_start: int | None = None
    page_end: int | None = None


class TenderSections(BaseModel):
    sections: list[TenderSection] = Field(default_factory=list)


# ── preliminary_evaluation.json ───────────────────────────────

class PrelimItem(BaseModel):
    item_id: str
    clause_text: str
    clause_strength: str
    fatal_if_unmet: bool = False
    section_anchor: str | None = None
    page_no: int | None = None
    cross_refs: list[str] = Field(default_factory=list)


class PreliminaryEvaluation(BaseModel):
    items: list[PrelimItem] = Field(default_factory=list)
    fatal_count: int = 0


# ── key_personnel_constraints.json ────────────────────────────

class PersonnelConstraint(BaseModel):
    role: str
    title_required: str | None = None
    cert_required: str | None = None
    no_active_project: bool = False
    social_security_months: int | None = None
    min_experience_years: int | None = None
    source_clause: str | None = None


class KeyPersonnelConstraints(BaseModel):
    constraints: list[PersonnelConstraint] = Field(default_factory=list)


# ── format_signature_constraints.json ─────────────────────────

class FormatSignatureConstraints(BaseModel):
    paper_copies: int | None = None
    electronic_copies: int | None = None
    binding_method: str | None = None
    seal_requirements: list[str] = Field(default_factory=list)
    signature_pages: list[str] = Field(default_factory=list)
    envelope_requirements: list[str] = Field(default_factory=list)
    format_clauses: list[str] = Field(default_factory=list)


# ── scoring_model.json ────────────────────────────────────────

class ScoringItem(BaseModel):
    item_id: str
    category: str
    description: str
    max_score: float
    weight: float | None = None
    evaluation_criteria: str | None = None
    section_anchor: str | None = None


class ScoringModel(BaseModel):
    total_score: float = 100.0
    items: list[ScoringItem] = Field(default_factory=list)


# ── technical_requirements.json ───────────────────────────────

class TechnicalRequirement(BaseModel):
    req_id: str
    category: str
    description: str
    is_mandatory: bool = False
    voltage_level: str | None = None
    engineering_type: str | None = None
    deviation_tracking: str | None = None
    section_anchor: str | None = None


class TechnicalRequirements(BaseModel):
    requirements: list[TechnicalRequirement] = Field(default_factory=list)


# ── deviation_tables.json ─────────────────────────────────────

class DeviationEntry(BaseModel):
    req_id: str
    requirement_text: str
    response_status: str = "PENDING"
    deviation_type: str | None = None
    deviation_detail: str | None = None
    risk_level: str = "low"


class DeviationTables(BaseModel):
    commercial_deviations: list[DeviationEntry] = Field(default_factory=list)
    technical_deviations: list[DeviationEntry] = Field(default_factory=list)


# ── compliance_check.json ─────────────────────────────────────

class ComplianceItem(BaseModel):
    item_id: str
    clause_text: str
    check_type: str  # "preliminary" or "detailed"
    status: str = "PENDING"
    risk_note: str | None = None


class ComplianceCheck(BaseModel):
    preliminary: list[ComplianceItem] = Field(default_factory=list)
    detailed: list[ComplianceItem] = Field(default_factory=list)


# ── fatal_gate_report.json ────────────────────────────────────

class FatalCheckResult(BaseModel):
    item_id: str
    clause_text: str
    asset_matched: bool = False
    match_detail: str | None = None
    blocked: bool = False
    risk_level: str = "WARN"
    category: str = "general"


class FatalGateReport(BaseModel):
    passed: bool = True
    blocked_reasons: list[str] = Field(default_factory=list)
    checks: list[FatalCheckResult] = Field(default_factory=list)
    power_scan_results: list["PowerScanHit"] = Field(default_factory=list)


class PowerScanHit(BaseModel):
    """A disqualification clause identified by the power scanner."""
    clause_text: str
    risk_level: str = "WARN"
    category: str = "general"
    source_offset: int = 0
    pattern_id: str = ""


# ── bid_blueprint.json ────────────────────────────────────────

class BlueprintTask(BaseModel):
    task_id: str
    priority: str  # "P00", "P01", "P02", ...
    title: str
    description: str
    section_key: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class RetrievalPolicy(BaseModel):
    hard_filters: dict[str, str] = Field(default_factory=dict)
    preferred_tags: list[str] = Field(default_factory=list)


class BidBlueprint(BaseModel):
    tender_id: str
    tasks: list[BlueprintTask] = Field(default_factory=list)
    retrieval_policy: RetrievalPolicy = Field(default_factory=RetrievalPolicy)
    administrative_checklist: list[str] = Field(default_factory=list)


# ── import_report.json ────────────────────────────────────────

class StepReport(BaseModel):
    step: str
    status: str
    duration_ms: int | None = None
    detail: str | None = None


class ImportReport(BaseModel):
    tender_id: str
    filename: str
    steps: list[StepReport] = Field(default_factory=list)
    final_status: str = "PENDING"
    fatal_blocked: bool = False
    derived_files: list[str] = Field(default_factory=list)
