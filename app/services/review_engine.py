from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models.tables import Requirement, ReviewReport, SectionContent
from app.services.byok import resolve_profile_chain_for_task
from app.services.llm_gateway import compliance_review_with_ensemble, compliance_review_with_fallback_chain

logger = logging.getLogger(__name__)


_INCONSISTENCY_PATTERN = re.compile(r"(矛盾|冲突|不一致)", re.IGNORECASE)
_REWRITE_MARKERS = ("rewrite", "non_compliant", "fatal", "disqualify_missing", "not_covered", "缺失")
_ADJUST_MARKERS = ("warn", "warning", "adjust", "manual", "需人工")


def _as_requirement_code_set(requirements: list[Requirement]) -> set[str]:
    return {str(item.requirement_code).strip() for item in requirements if str(item.requirement_code).strip()}


def _as_modeled_issues(source_report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = source_report.get("modeled_issues", [])
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _missing_requirements_from_issues(modeled_issues: list[dict[str, Any]]) -> set[str]:
    missing: set[str] = set()
    for issue in modeled_issues:
        code = str(issue.get("requirement_code", "")).strip()
        issue_type = str(issue.get("issue_type", "")).strip().upper()
        if not code:
            continue
        if issue_type in {"MISSING", "NON_COMPLIANT"}:
            missing.add(code)
    return missing


def _logical_inconsistencies_from_issues(modeled_issues: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for issue in modeled_issues:
        desc = str(issue.get("description", "")).strip()
        issue_type = str(issue.get("issue_type", "")).strip().upper()
        if not desc:
            continue
        if issue_type == "LOGICAL_INCONSISTENCY" or _INCONSISTENCY_PATTERN.search(desc):
            items.append(desc)
    return items


def _risk_points_from_issues(modeled_issues: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for issue in modeled_issues:
        desc = str(issue.get("description", "")).strip()
        if desc:
            points.append(desc)
    return points


def resolve_triage_gate(
    *,
    review_status: str | None,
    review_report: dict[str, Any] | None,
    warnings: list[str],
    disqualify_coverage_ok: bool,
) -> str:
    normalized_status = str(review_status or "").strip().upper()
    if not disqualify_coverage_ok:
        return "REWRITE"
    if normalized_status in {"REWRITE", "FAIL"}:
        return "REWRITE"

    issues_raw = review_report.get("issues", []) if isinstance(review_report, dict) else []
    issue_text = " ".join(str(item).lower() for item in issues_raw)
    if any(marker in issue_text for marker in _REWRITE_MARKERS):
        return "REWRITE"
    if any(marker in issue_text for marker in _ADJUST_MARKERS):
        return "ADJUST_PASS"

    warnings_text = " ".join(str(item).lower() for item in warnings)
    if warnings and any(marker in warnings_text for marker in _REWRITE_MARKERS):
        return "REWRITE"
    if warnings:
        return "ADJUST_PASS"

    return "PASS"


def _section_coverage_map(
    *,
    sections: list[SectionContent],
    missing_requirements: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for section in sections:
        section_key = str(section.section_key)
        codes = [str(code).strip() for code in (section.requirement_codes or []) if str(code).strip()]
        if not codes:
            result[section_key] = {"mapped_requirements": 0, "coverage": 1.0}
            continue
        mapped = set(codes)
        missing = mapped & missing_requirements
        coverage = (len(mapped) - len(missing)) / len(mapped)
        result[section_key] = {
            "mapped_requirements": len(mapped),
            "missing_requirements": sorted(missing),
            "coverage": round(coverage, 4),
        }
    return result


def _build_full_review_report_payload(
    *,
    status: str,
    source_report: dict[str, Any],
    requirements: list[Requirement],
    sections: list[SectionContent],
) -> dict[str, Any]:
    requirement_codes = _as_requirement_code_set(requirements)
    modeled_issues = _as_modeled_issues(source_report)
    missing_requirements = _missing_requirements_from_issues(modeled_issues) & requirement_codes
    logical_inconsistencies = _logical_inconsistencies_from_issues(modeled_issues)
    risk_points = _risk_points_from_issues(modeled_issues)

    total = len(requirement_codes)
    covered = max(0, total - len(missing_requirements))
    coverage_estimate = (covered / total) if total else 0.0
    score_estimate = round(coverage_estimate * 100.0, 2)

    payload: dict[str, Any] = {
        "status": status,
        "general_comments": str(source_report.get("general_comments", "")).strip(),
        "modeled_issues": modeled_issues,
        "missing_requirements": sorted(missing_requirements),
        "logical_inconsistencies": logical_inconsistencies,
        "risk_points": risk_points,
        "coverage_estimate": round(coverage_estimate, 4),
        "score_estimate": score_estimate,
        "sections_reviewed": [str(section.section_key) for section in sections],
        "section_coverage": _section_coverage_map(
            sections=sections,
            missing_requirements=missing_requirements,
        ),
    }
    if "error" in source_report:
        payload["error"] = source_report["error"]
    return payload


def _requirements_payload(requirements: list[Requirement]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for requirement in requirements:
        payload.append(
            {
                "requirement_code": requirement.requirement_code,
                "strength": requirement.strength.name if hasattr(requirement.strength, "name") else str(requirement.strength),
                "original_text": requirement.original_text,
            }
        )
    return payload


def _full_document_text(sections: list[SectionContent]) -> str:
    chunks: list[str] = []
    for section in sections:
        chunks.append(f"[{section.section_key}] {section.section_title}\n{section.content_md}")
    return "\n\n".join(chunks)


class ComplianceReviewer:
    def __init__(self, db: Session):
        self.db = db

    def review_section(self, project_id: str, section_id: str) -> ReviewReport:
        """
        Run compliance review for a specific section against its mapped requirements.
        """
        pid = uuid.UUID(project_id)
        # 1. Load data
        stmt = select(SectionContent).where(
            SectionContent.id == uuid.UUID(section_id),
            SectionContent.project_id == pid
        )
        section = self.db.scalar(stmt)
        if not section:
            raise ValueError(f"Section {section_id} not found in project {project_id}")

        if not section.requirement_codes:
            logger.info("Section %s has no requirements mapped, skipping review.", section.section_key)
            return self._create_empty_report(project_id, section, "PASS", "No requirements mapped.")

        # 2. Load requirements
        # We assume requirement_codes are stored in SectionContent array.
        req_stmt = select(Requirement).where(
            Requirement.project_id == pid,
            Requirement.requirement_code.in_(section.requirement_codes)
        )
        requirements = self.db.scalars(req_stmt).all()
        
        if not requirements:
             logger.warning("Section %s has codes %s but no Requirement records found.", section.section_key, section.requirement_codes)
             return self._create_empty_report(project_id, section, "WARN", "Requirements not found in DB.")

        # 3. Prepare payload for LLM
        req_payload = _requirements_payload(requirements)

        # 4. Invoke LLM Gateway
        review_chain = resolve_profile_chain_for_task(project_id=project_id, task_type="REVIEW")
        
        try:
            result, idx = compliance_review_with_fallback_chain(
                profile_chain=review_chain,
                project_id=project_id,
                content_text=section.content_md,
                requirements=req_payload
            )
            status = result.status
            report_json = result.report
        except Exception as e:
            logger.error("Compliance review failed: %s", e)
            status = "FAIL"
            report_json = {"error": str(e)}

        # 5. Save Report
        # Check if report exists for this section? Or just create new.
        # usually one report per version? But ReviewReport doesn't link to section version yet in my minimal model.
        # It links to section_key.
        
        report = ReviewReport(
            project_id=pid,
            section_key=section.section_key,
            outline_id=section.section_key, # simplistic mapping
            status=status,
            report_json=report_json
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def review_full_document(
        self,
        project_id: str,
        outline_id: str | None = None,
        *,
        enable_ensemble: bool = False,
        ensemble_size: int | None = None,
    ) -> ReviewReport:
        pid = uuid.UUID(project_id)

        sections = self.db.scalars(
            select(SectionContent)
            .where(SectionContent.project_id == pid)
            .order_by(SectionContent.section_key.asc())
        ).all()
        if not sections:
            raise ValueError(f"No section content found in project {project_id}")

        requirements = self.db.scalars(
            select(Requirement).where(Requirement.project_id == pid)
        ).all()
        if not requirements:
            source = {"general_comments": "No requirements found in DB.", "modeled_issues": []}
            payload = _build_full_review_report_payload(
                status="WARN",
                source_report=source,
                requirements=[],
                sections=sections,
            )
            report = ReviewReport(
                project_id=pid,
                section_key="__FULL__",
                outline_id=outline_id or "__FULL__",
                status="WARN",
                report_json=payload,
            )
            self.db.add(report)
            self.db.commit()
            self.db.refresh(report)
            return report

        review_chain = resolve_profile_chain_for_task(project_id=project_id, task_type="REVIEW")
        try:
            if enable_ensemble:
                result, _ = compliance_review_with_ensemble(
                    profile_chain=review_chain,
                    project_id=project_id,
                    content_text=_full_document_text(sections),
                    requirements=_requirements_payload(requirements),
                    ensemble_size=ensemble_size or 3,
                )
            else:
                result, _ = compliance_review_with_fallback_chain(
                    profile_chain=review_chain,
                    project_id=project_id,
                    content_text=_full_document_text(sections),
                    requirements=_requirements_payload(requirements),
                )
            status = result.status
            source_report = result.report if isinstance(result.report, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Full compliance review failed: %s", exc)
            status = "FAIL"
            source_report = {"error": str(exc), "modeled_issues": []}

        report = ReviewReport(
            project_id=pid,
            section_key="__FULL__",
            outline_id=outline_id or "__FULL__",
            status=status,
            report_json=_build_full_review_report_payload(
                status=status,
                source_report=source_report,
                requirements=requirements,
                sections=sections,
            ),
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def _create_empty_report(self, project_id: str, section: SectionContent, status: str, msg: str) -> ReviewReport:
        pid = uuid.UUID(project_id)
        report = ReviewReport(
            project_id=pid,
            section_key=section.section_key,
            outline_id=section.section_key,
            status=status,
            report_json={"general_comments": msg, "modeled_issues": []}
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report


def run_compliance_review(project_id: str, section_key: str) -> ReviewReport:
    """Orchestrate compliance review with session management."""
    with session_scope() as db:
        stmt = select(SectionContent).where(
            SectionContent.project_id == uuid.UUID(project_id),
            SectionContent.section_key == section_key
        )
        section = db.scalar(stmt)
        if not section:
            raise ValueError(f"Section {section_key} not found in project {project_id}")

        reviewer = ComplianceReviewer(db)
        return reviewer.review_section(project_id, str(section.id))


def run_full_compliance_review(
    project_id: str,
    outline_id: str | None = None,
    *,
    enable_ensemble: bool = False,
    ensemble_size: int | None = None,
) -> ReviewReport:
    with session_scope() as db:
        reviewer = ComplianceReviewer(db)
        return reviewer.review_full_document(
            project_id=project_id,
            outline_id=outline_id,
            enable_ensemble=enable_ensemble,
            ensemble_size=ensemble_size,
        )
