from __future__ import annotations

import re
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.tables import Requirement, ReviewReport, ScoringReport, SectionContent

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {item.lower() for item in TOKEN_PATTERN.findall(text or "") if item}


def _estimate_requirement_coverage(
    requirement_text: str,
    section_text: str,
) -> tuple[bool, float]:
    section_text = section_text or ""
    if not section_text.strip():
        return False, 0.0

    req_tokens = _tokenize(requirement_text)
    section_tokens = _tokenize(section_text)
    if req_tokens:
        overlap = len(req_tokens & section_tokens) / len(req_tokens)
        if overlap >= 0.4:
            return True, min(0.9, 0.55 + overlap * 0.5)

    for phrase in re.findall(r"[\u4e00-\u9fff]{2,8}", requirement_text or ""):
        if phrase in section_text:
            return True, 0.65

    chinese_chars = "".join(re.findall(r"[\u4e00-\u9fff]", requirement_text or ""))
    if len(chinese_chars) >= 4:
        overlap_bigrams = 0
        for idx in range(len(chinese_chars) - 1):
            gram = chinese_chars[idx : idx + 2]
            if gram in section_text:
                overlap_bigrams += 1
                if overlap_bigrams >= 2:
                    return True, 0.6

    if len(section_text.strip()) >= 120:
        return True, 0.55
    return False, 0.0


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
                estimated_pass, confidence = _estimate_requirement_coverage(
                    str(getattr(r, "original_text", "") or ""),
                    str(getattr(section, "content_md", "") or ""),
                )
                if estimated_pass:
                    estimated_score = round(weight * min(max(confidence, 0.5), 0.85), 2)
                    total_score += estimated_score
                    details.append(
                        {
                            "code": r.requirement_code,
                            "score": estimated_score,
                            "status": "ESTIMATED_PASS",
                            "section": section.section_key,
                            "confidence": round(confidence, 4),
                            "reason": "estimated_from_section_without_review",
                        }
                    )
                else:
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
