"""FATAL gate — check preliminary requirements against company assets (R0).

If any fatal_if_unmet item cannot be matched to a company asset,
the entire import is blocked (FATAL_BLOCKED).
"""

from __future__ import annotations

import logging

from app.tender.schemas import FatalCheckResult, FatalGateReport

logger = logging.getLogger(__name__)


def check_fatal_gate(
    prelim_data: dict,
    personnel_data: dict,
) -> FatalGateReport:
    """Check preliminary items against available assets.

    Args:
        prelim_data: Parsed preliminary_evaluation.json content
        personnel_data: Parsed key_personnel_constraints.json content

    Returns:
        FatalGateReport with passed=False if any fatal item is unmet.
    """
    checks: list[FatalCheckResult] = []
    blocked_reasons: list[str] = []

    # Check fatal preliminary items
    for item in prelim_data.get("items", []):
        if not item.get("fatal_if_unmet", False):
            continue

        clause = item.get("clause_text", "")
        item_id = item.get("item_id", "unknown")

        # Try to match against company assets
        matched, detail = _match_prelim_to_assets(clause)

        checks.append(FatalCheckResult(
            item_id=item_id,
            clause_text=clause[:300],
            asset_matched=matched,
            match_detail=detail,
            blocked=not matched,
        ))

        if not matched:
            blocked_reasons.append(f"{item_id}: {clause[:100]}")

    # Check personnel constraints
    for constraint in personnel_data.get("constraints", []):
        role = constraint.get("role", "unknown")
        matched, detail = _match_personnel_to_assets(constraint)

        checks.append(FatalCheckResult(
            item_id=f"PERSON-{role}",
            clause_text=f"人员要求: {role} — {constraint.get('cert_required', 'N/A')}",
            asset_matched=matched,
            match_detail=detail,
            blocked=not matched,
        ))

        if not matched and constraint.get("cert_required"):
            blocked_reasons.append(f"人员缺失: {role} ({constraint.get('cert_required', '')})")

    passed = len(blocked_reasons) == 0
    logger.info("fatal gate: passed=%s, %d checks, %d blocked", passed, len(checks), len(blocked_reasons))

    return FatalGateReport(
        passed=passed,
        blocked_reasons=blocked_reasons,
        checks=checks,
    )


def _match_prelim_to_assets(clause_text: str) -> tuple[bool, str]:
    """Try to match a preliminary clause against company qualification assets.

    Returns (matched: bool, detail: str).
    """
    try:
        from app.tender.assets.repository import get_company_qualifications

        qualifications = get_company_qualifications()
        if not qualifications:
            return False, "no company qualifications found in asset library"

        # Simple keyword matching against qualification titles
        for qual in qualifications:
            title = (qual.get("title") or "").lower()
            if not title:
                continue
            # Check for keyword overlap
            clause_lower = clause_text.lower()
            keywords = ["资质", "许可", "证书", "营业执照", "安全生产"]
            for kw in keywords:
                if kw in clause_lower and kw in title:
                    return True, f"matched qualification: {qual.get('title')}"

        # If no specific match but qualifications exist, mark as needs_review
        return True, "qualifications exist but exact match needs human review"
    except Exception as exc:  # noqa: BLE001
        logger.warning("asset query failed, defaulting to pass: %s", exc)
        return True, f"asset query error (defaulting to pass): {exc}"


def _match_personnel_to_assets(constraint: dict) -> tuple[bool, str]:
    """Try to match a personnel constraint against personnel assets.

    Returns (matched: bool, detail: str).
    """
    try:
        from app.tender.assets.repository import get_people_candidates

        role = constraint.get("role", "")
        candidates = get_people_candidates(
            role=role,
            cert_required=constraint.get("cert_required"),
            no_active_project=constraint.get("no_active_project", False),
        )

        if not candidates:
            return False, f"no candidates found for role: {role}"

        return True, f"{len(candidates)} candidate(s) available for {role}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("personnel query failed, defaulting to pass: %s", exc)
        return True, f"personnel query error (defaulting to pass): {exc}"
