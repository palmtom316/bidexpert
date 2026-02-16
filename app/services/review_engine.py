from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.tables import Requirement, ReviewReport, SectionContent
from app.services.byok import resolve_profile_chain_for_task
from app.services.llm_gateway import compliance_review_with_fallback_chain

logger = logging.getLogger(__name__)


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
        req_payload = []
        for r in requirements:
            req_payload.append({
                "requirement_code": r.requirement_code,
                "strength": r.strength.name if hasattr(r.strength, "name") else str(r.strength),
                "original_text": r.original_text,
            })

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
    with SessionLocal() as db:
        stmt = select(SectionContent).where(
            SectionContent.project_id == uuid.UUID(project_id),
            SectionContent.section_key == section_key
        )
        section = db.scalar(stmt)
        if not section:
            raise ValueError(f"Section {section_key} not found in project {project_id}")

        reviewer = ComplianceReviewer(db)
        return reviewer.review_section(project_id, str(section.id))
