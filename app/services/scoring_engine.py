from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.tables import Requirement, ReviewReport, ScoringReport, SectionContent


class SimulatedScorer:
    def __init__(self, db: Session):
        self.db = db

    def calculate_score(self, project_id: str) -> ScoringReport:
        # 1. Load data
        pid = uuid.UUID(project_id)
        reqs = self.db.scalars(
             select(Requirement).where(Requirement.project_id == pid)
        ).all()
        
        sections = self.db.scalars(
             select(SectionContent).where(SectionContent.project_id == pid)
        ).all()
        
        reports = self.db.scalars(
             select(ReviewReport).where(ReviewReport.project_id == pid)
        ).all()

        # 2. Build indices
        code_to_section = {}
        for s in sections:
            if s.requirement_codes:
                # Handle varying formats if necessary (e.g. CSV or list)
                codes = s.requirement_codes if isinstance(s.requirement_codes, list) else []
                for c in codes:
                    code_to_section[c] = s

        reports_by_key = {}
        # Sort by created_at to get latest
        sorted_reports = sorted(reports, key=lambda x: x.created_at or datetime.min)
        for r in sorted_reports:
             reports_by_key[r.section_key] = r

        # 3. Calculate
        total_score = 0.0
        max_possible_score = 0.0
        details = []

        for r in reqs:
            weight = float(r.score_weight or 0.0)
            max_possible_score += weight
            
            section = code_to_section.get(r.requirement_code)
            
            if not section:
                details.append({"code": r.requirement_code, "score": 0, "status": "UNPLANNED", "section": None})
                continue
            
            report = reports_by_key.get(section.section_key)
            if not report:
                details.append({"code": r.requirement_code, "score": 0, "status": "UNREVIEWED", "section": section.section_key})
                continue

            # Evaluate
            passed = False
            status = "FAIL"
            reason = None

            if report.status == "PASS":
                passed = True
                status = "PASS"
            else:
                # Check granular issues
                issues = report.report_json.get("modeled_issues", [])
                
                # Check if generic error
                is_generic_error = any(
                    isinstance(i, dict) and i.get("requirement_code") == "PARSE_ERROR" 
                    for i in issues
                )
                
                if is_generic_error:
                    status = "ERROR"
                    reason = "Review generation failed"
                else:
                    # Look for specific violation
                    violation = next((i for i in issues if isinstance(i, dict) and i.get("requirement_code") == r.requirement_code), None)
                    if violation:
                        status = "FAIL"
                        reason = violation.get("description")
                    else:
                        # Implicit pass
                        passed = True
                        status = "PASS"

            if passed:
                total_score += weight
                details.append({"code": r.requirement_code, "score": weight, "status": "PASS", "section": section.section_key})
            else:
                details.append({"code": r.requirement_code, "score": 0, "status": status, "section": section.section_key, "reason": reason})

        # 4. Save
        sr = ScoringReport(
            project_id=pid,
            score_total=total_score,
            details_json={
                "items": details, 
                "max_possible": max_possible_score,
                "percentage": (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
            }
        )
        self.db.add(sr)
        self.db.commit()
        self.db.refresh(sr)
        return sr


def run_scoring_service(project_id: str) -> ScoringReport:
    with SessionLocal() as db:
        scorer = SimulatedScorer(db)
        return scorer.calculate_score(project_id)
