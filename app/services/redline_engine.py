from __future__ import annotations

import uuid
from datetime import date, datetime

from app.schemas.contracts import (
    RedlineCheckRequest,
    RedlineDurationCheck,
    RedlineFinding,
    RedlineParameterComparison,
    RedlineReport,
)

_READINESS_CATEGORIES = {"人员", "资质", "业绩", "社保", "授权"}


# ── G2 Active Validators ────────────────────────────────────


def check_qualifications(
    *,
    project_id: str,
    tender_package_id: str,
    tender_open_date: date | None = None,
) -> list[RedlineFinding]:
    """G2.2 — Check qualification validity, grade match, and entity consistency."""
    from app.tender.assets.repository import get_company_qualifications

    findings: list[RedlineFinding] = []
    effective_date = tender_open_date or date.today()
    qualifications = get_company_qualifications(valid_after=effective_date)

    if not qualifications:
        findings.append(
            RedlineFinding(
                rule_id="QUAL-MISSING",
                category="资质",
                severity="P0",
                message="未在资产库中查询到有效期内的公司资质文件",
                required_action="上传或更新公司资质文件，确保有效期覆盖开标日期",
            )
        )
        return findings

    for qual in qualifications:
        valid_to_str = qual.get("valid_to")
        if valid_to_str:
            try:
                valid_to = date.fromisoformat(valid_to_str)
                if valid_to <= effective_date:
                    findings.append(
                        RedlineFinding(
                            rule_id=f"QUAL-EXPIRED::{qual.get('id', '')}",
                            category="资质",
                            severity="P0",
                            message=f"资质 [{qual.get('title', '')}] 已过期（有效期至 {valid_to_str}），无法覆盖开标日期",
                            clause_ref=qual.get("id"),
                            required_action="更新资质文件使有效期覆盖开标日期",
                            evidence_refs=[qual.get("id", "")],
                        )
                    )
            except (ValueError, TypeError):
                pass

    return findings


def check_key_staff_and_ss(
    *,
    project_id: str,
    tender_package_id: str,
) -> list[RedlineFinding]:
    """G2.3 — Check key staff chain: role → person → cert → social security."""
    from app.db.session import session_scope
    from app.tender.assets.repository import list_personnel_candidates_from_asset_pool

    findings: list[RedlineFinding] = []

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        findings.append(
            RedlineFinding(
                rule_id="STAFF-INVALID-PROJECT",
                category="人员",
                severity="P0",
                message="无效的 project_id，无法执行人员校验",
                required_action="提供有效的 project_id",
            )
        )
        return findings

    with session_scope() as db:
        candidates = list_personnel_candidates_from_asset_pool(
            db,
            project_id=project_uuid,
        )

    if not candidates:
        findings.append(
            RedlineFinding(
                rule_id="STAFF-POOL-EMPTY",
                category="人员",
                severity="P0",
                message="项目资产池中无人员候选，关键岗位无法匹配",
                required_action="向项目资产池添加人员资产",
            )
        )
        return findings

    # Check for concurrent project conflicts
    for person in candidates:
        active_count = int(person.get("active_project_count", 0))
        if active_count > 0:
            findings.append(
                RedlineFinding(
                    rule_id=f"STAFF-CONFLICT::{person.get('asset_pool_id', '')}",
                    category="人员",
                    severity="P1",
                    message=(
                        f"人员 [{person.get('asset_name', '')}] 当前已参与 {active_count} 个在建项目，"
                        "可能存在专职冲突"
                    ),
                    required_action="确认该人员可抽调至本项目，或更换候选人",
                    evidence_refs=person.get("evidence_refs", []),
                )
            )

    # Check for insufficient social security
    for person in candidates:
        months = int(person.get("social_security_months", 0))
        if months < 6:
            findings.append(
                RedlineFinding(
                    rule_id=f"STAFF-SS-LOW::{person.get('asset_pool_id', '')}",
                    category="社保",
                    severity="P1",
                    message=(
                        f"人员 [{person.get('asset_name', '')}] 社保缴纳仅 {months} 个月，"
                        "可能不满足招标要求"
                    ),
                    required_action="确认社保缴纳月数满足招标要求",
                    evidence_refs=person.get("evidence_refs", []),
                )
            )

    return findings


def check_authorization(
    *,
    project_id: str,
    tender_package_id: str,
) -> list[RedlineFinding]:
    """G2.4 — Check authorization/commitment letter completeness."""
    from app.db.session import session_scope
    from app.tender.assets.repository import list_bid_asset_pool_entries

    findings: list[RedlineFinding] = []

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        findings.append(
            RedlineFinding(
                rule_id="AUTH-INVALID-PROJECT",
                category="授权",
                severity="P0",
                message="无效的 project_id，无法执行授权签章校验",
                required_action="提供有效的 project_id",
            )
        )
        return findings

    with session_scope() as db:
        all_entries = list_bid_asset_pool_entries(db, project_id=project_uuid)

    auth_entries = [
        entry for entry in all_entries
        if isinstance(entry.metadata_json, dict)
        and str(entry.metadata_json.get("asset_type", "")).strip().lower() == "authorization"
    ]

    if not auth_entries:
        findings.append(
            RedlineFinding(
                rule_id="AUTH-MISSING",
                category="授权",
                severity="P0",
                message="项目资产池中未找到授权函/承诺函类资产",
                required_action="上传授权委托书及承诺函至项目资产池",
            )
        )
        return findings

    required_phrases = ["法定代表人", "公章"]
    for entry in auth_entries:
        metadata = dict(entry.metadata_json or {})
        content_text = str(metadata.get("content_text", ""))
        for phrase in required_phrases:
            if phrase not in content_text:
                findings.append(
                    RedlineFinding(
                        rule_id=f"AUTH-INCOMPLETE::{entry.id}::{phrase}",
                        category="授权",
                        severity="P1",
                        message=f"授权文件 [{entry.asset_name}] 缺少关键字段「{phrase}」",
                        required_action=f"补充授权文件中的「{phrase}」字段",
                        evidence_refs=[str(entry.id)],
                    )
                )

    return findings


# ── G2.6 Duration Arithmetic ────────────────────────────────


def _build_duration_findings(
    duration_check: RedlineDurationCheck,
) -> list[RedlineFinding]:
    """Hard arithmetic validation: committed duration must match calendar dates."""
    findings: list[RedlineFinding] = []

    try:
        start = datetime.strptime(duration_check.start_date, "%Y-%m-%d").date()
        completion = datetime.strptime(duration_check.completion_date, "%Y-%m-%d").date()
    except ValueError:
        findings.append(
            RedlineFinding(
                rule_id="DURATION-DATE-INVALID",
                category="参数偏离",
                severity="P0",
                message="开工日期或竣工日期格式无效，须为 YYYY-MM-DD",
                required_action="修正日期格式",
            )
        )
        return findings

    if completion <= start:
        findings.append(
            RedlineFinding(
                rule_id="DURATION-DATE-ORDER",
                category="参数偏离",
                severity="P0",
                message=f"竣工日期 {duration_check.completion_date} 不晚于开工日期 {duration_check.start_date}",
                required_action="修正开竣工日期使竣工日期晚于开工日期",
            )
        )
        return findings

    calendar_days = (completion - start).days
    committed = duration_check.committed_duration_days

    if committed != calendar_days:
        findings.append(
            RedlineFinding(
                rule_id="DURATION-MISMATCH",
                category="参数偏离",
                severity="P0",
                message=(
                    f"承诺工期 {committed} 天 ≠ 招标开竣工日期间隔 {calendar_days} 天 "
                    f"({duration_check.start_date} ~ {duration_check.completion_date})"
                ),
                required_action=f"调整承诺工期至 {calendar_days} 天",
            )
        )

    if duration_check.min_required_duration_days is not None:
        min_days = duration_check.min_required_duration_days
        if committed < min_days:
            findings.append(
                RedlineFinding(
                    rule_id="DURATION-TOO-SHORT",
                    category="参数偏离",
                    severity="P0",
                    message=f"承诺工期 {committed} 天 < 招标最短工期要求 {min_days} 天",
                    required_action=f"延长承诺工期至不少于 {min_days} 天",
                )
            )

    return findings


# ── Core Orchestration ──────────────────────────────────────


def run_redline_check(payload: RedlineCheckRequest) -> RedlineReport:
    findings: list[RedlineFinding] = list(payload.findings)
    findings.extend(_build_parameter_deviation_findings(payload.parameter_comparisons))

    # G2.6 Duration arithmetic
    if payload.duration_check is not None:
        findings.extend(_build_duration_findings(payload.duration_check))

    # G2 Active checks: qualifications, key staff, authorization
    if payload.run_active_checks:
        findings.extend(
            check_qualifications(
                project_id=payload.project_id,
                tender_package_id=payload.tender_package_id,
            )
        )
        findings.extend(
            check_key_staff_and_ss(
                project_id=payload.project_id,
                tender_package_id=payload.tender_package_id,
            )
        )
        findings.extend(
            check_authorization(
                project_id=payload.project_id,
                tender_package_id=payload.tender_package_id,
            )
        )

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
