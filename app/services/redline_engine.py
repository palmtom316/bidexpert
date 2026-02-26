from __future__ import annotations

from app.schemas.contracts import (
    RedlineCheckRequest,
    RedlineFinding,
    RedlineParameterComparison,
    RedlineReport,
)

_READINESS_CATEGORIES = {"人员", "资质", "业绩", "社保"}


def run_redline_check(payload: RedlineCheckRequest) -> RedlineReport:
    findings: list[RedlineFinding] = list(payload.findings)
    findings.extend(_build_parameter_deviation_findings(payload.parameter_comparisons))

    has_p0 = any(item.severity == "P0" for item in findings)
    has_p1 = any(item.severity == "P1" for item in findings)
    status = "BLOCKED" if has_p0 else ("NEED_FIX" if has_p1 else "PASS")
    readiness = _build_readiness_missing_items(findings, payload.required_documents, payload.provided_documents)

    return RedlineReport(
        status=status,
        summary=f"完成红线审查，发现 {len(findings)} 项风险。",
        readiness_missing_items=readiness,
        findings=findings,
    )


def _build_parameter_deviation_findings(
    comparisons: list[RedlineParameterComparison],
) -> list[RedlineFinding]:
    results: list[RedlineFinding] = []
    for item in comparisons:
        if item.provided_value >= item.required_value:
            continue
        unit_suffix = f" {item.unit}" if item.unit else ""
        results.append(
            RedlineFinding(
                rule_id=f"NEG-DEV::{item.parameter_name}",
                category="参数偏离",
                severity="P0",
                message=(
                    f"{item.parameter_name} 出现负偏离：承诺值 {item.provided_value}{unit_suffix} "
                    f"< 招标要求 {item.required_value}{unit_suffix}"
                ),
                required_action=f"将 {item.parameter_name} 调整到不低于招标要求并补充证据",
            )
        )
    return results


def _build_readiness_missing_items(
    findings: list[RedlineFinding],
    required_documents: list[str],
    provided_documents: list[str],
) -> list[str]:
    missing_items: set[str] = set()
    for finding in findings:
        if finding.category in _READINESS_CATEGORIES and finding.severity in {"P0", "P1"}:
            if finding.required_action:
                missing_items.add(finding.required_action.strip())

    provided_set = {item.strip() for item in provided_documents if item and item.strip()}
    for required in required_documents:
        normalized = required.strip()
        if normalized and normalized not in provided_set:
            missing_items.add(f"缺{normalized}")

    return sorted(item for item in missing_items if item)
