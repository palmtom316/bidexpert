"""FATAL gate — check preliminary requirements against company assets (R0).

Enhanced with power engineering disqualification clause identification.
Scans tender text for clauses that can cause bid rejection (废标) in
power engineering projects, with three-tier risk grading.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import NamedTuple

from app.tender.schemas import (
    FatalCheckResult,
    FatalGateReport,
    PowerScanHit,
)

logger = logging.getLogger(__name__)


# ── Risk levels ──────────────────────────────────────────────


class RiskLevel(StrEnum):
    """Disqualification risk severity."""

    FATAL = "FATAL"   # Direct bid rejection (废标)
    HIGH = "HIGH"     # High probability of rejection
    WARN = "WARN"     # Needs human confirmation


# ── Clause pattern definitions ───────────────────────────────

class _ClausePattern(NamedTuple):
    """A disqualification clause detection pattern."""

    pattern_id: str
    category: str
    risk_level: RiskLevel
    keywords: tuple[str, ...]
    regex: re.Pattern[str] | None = None


# Rejection context markers — when these appear near a keyword,
# the clause is a hard rejection (FATAL), not just advisory.
_REJECTION_MARKERS: tuple[str, ...] = (
    "废标", "否决", "拒绝", "无效", "不予受理", "不予通过",
    "不得参与", "取消资格", "不具备", "不予接受", "不合格",
    "按废标处理", "视为无效", "不予评审",
)

# Advisory/scoring markers — these indicate scoring impact, not rejection.
_ADVISORY_MARKERS: tuple[str, ...] = (
    "酌情扣分", "适当扣分", "宜", "建议", "优先考虑", "加分",
)

# ── Power engineering disqualification clause knowledge base ──

_POWER_CLAUSE_PATTERNS: tuple[_ClausePattern, ...] = (
    # --- Qualification & license ---
    _ClausePattern(
        "QUAL_SAFETY_LICENSE",
        "safety_license",
        RiskLevel.FATAL,
        ("安全生产许可证",),
    ),
    _ClausePattern(
        "QUAL_POWER_GENERAL",
        "qualification",
        RiskLevel.FATAL,
        ("电力工程施工总承包",),
        re.compile(r"电力工程施工总承包[一壹二贰三叁]级"),
    ),
    _ClausePattern(
        "QUAL_ELECTRICAL_INSTALL",
        "qualification",
        RiskLevel.FATAL,
        ("电力设施安装", "承装承修承试"),
        re.compile(r"承装[（(]修[、,]试[）)].*?[一二三四五]级"),
    ),
    _ClausePattern(
        "QUAL_BUSINESS_LICENSE",
        "business_license",
        RiskLevel.FATAL,
        ("营业执照",),
    ),
    _ClausePattern(
        "QUAL_GENERAL",
        "qualification",
        RiskLevel.FATAL,
        ("资质等级", "资质要求", "资质证书"),
    ),

    # --- Bid bond & procedural ---
    _ClausePattern(
        "PROC_BID_BOND",
        "bid_bond",
        RiskLevel.FATAL,
        ("投标保证金",),
        re.compile(r"投标保证金.*?(?:万元|元)"),
    ),
    _ClausePattern(
        "PROC_BID_VALIDITY",
        "bid_validity",
        RiskLevel.HIGH,
        ("投标有效期",),
        re.compile(r"投标有效期.*?\d+.*?天"),
    ),
    _ClausePattern(
        "PROC_SEAL_SIGNATURE",
        "format_compliance",
        RiskLevel.FATAL,
        ("法定代表人签字", "加盖公章", "投标文件签章"),
    ),

    # --- Personnel ---
    _ClausePattern(
        "PERSON_CONSTRUCTOR",
        "personnel",
        RiskLevel.FATAL,
        ("一级建造师", "二级建造师"),
        re.compile(r"[一二]级建造师.*?(?:机电|电力|市政)"),
    ),
    _ClausePattern(
        "PERSON_SPECIAL_OPS",
        "special_operator",
        RiskLevel.FATAL,
        ("特种作业", "操作证", "电工证"),
        re.compile(r"特种作业.*?(?:电工|高处|焊接|吊装)"),
    ),
    _ClausePattern(
        "PERSON_SAFETY_OFFICER",
        "personnel",
        RiskLevel.HIGH,
        ("专职安全员", "安全生产管理人员"),
    ),

    # --- Power-industry-specific ---
    _ClausePattern(
        "POWER_VOLTAGE_PERF",
        "voltage_performance",
        RiskLevel.FATAL,
        ("电压等级",),
        re.compile(r"(?:110|220|330|500|750|1000)\s*kV.*?(?:业绩|经验|施工)"),
    ),
    _ClausePattern(
        "POWER_GRID_CONNECTION",
        "grid_connection",
        RiskLevel.HIGH,
        ("并网验收", "并网调试"),
    ),
    _ClausePattern(
        "POWER_RELAY_PROTECTION",
        "relay_protection",
        RiskLevel.HIGH,
        ("继电保护", "保护整定"),
    ),
    _ClausePattern(
        "POWER_LIVE_WORK",
        "live_work",
        RiskLevel.FATAL,
        ("带电作业",),
    ),
    _ClausePattern(
        "POWER_FACILITY_ZONE",
        "facility_protection",
        RiskLevel.HIGH,
        ("电力设施保护区",),
    ),
    _ClausePattern(
        "POWER_SUBSTATION",
        "substation",
        RiskLevel.HIGH,
        ("变电站", "变电所", "开关站"),
        re.compile(r"(?:变电站|变电所|开关站).*?(?:施工|安装|调试)"),
    ),
    _ClausePattern(
        "POWER_TRANSMISSION",
        "transmission_line",
        RiskLevel.HIGH,
        ("架空线路", "输电线路", "电缆线路"),
        re.compile(r"(?:架空|输电|电缆)线路.*?(?:施工|架设|敷设)"),
    ),
    _ClausePattern(
        "POWER_GROUNDING",
        "grounding",
        RiskLevel.HIGH,
        ("接地装置", "接地电阻", "接地网"),
    ),
    _ClausePattern(
        "POWER_SAFETY_TOOLS",
        "safety_tools",
        RiskLevel.HIGH,
        ("安全工器具", "绝缘工具"),
        re.compile(r"(?:安全工器具|绝缘工具).*?检测"),
    ),
    _ClausePattern(
        "POWER_COMMISSIONING",
        "commissioning",
        RiskLevel.HIGH,
        ("投运", "送电", "通电"),
        re.compile(r"(?:投运|送电|通电).*?(?:期限|日期|时间|节点)"),
    ),

    # --- Performance & track record ---
    _ClausePattern(
        "PERF_SIMILAR_PROJECT",
        "similar_performance",
        RiskLevel.HIGH,
        ("类似工程", "类似项目", "同类工程"),
        re.compile(r"(?:类似|同类)(?:工程|项目).*?(?:业绩|经验)"),
    ),
    _ClausePattern(
        "PERF_CONTRACT_VALUE",
        "contract_performance",
        RiskLevel.HIGH,
        ("合同金额", "合同额"),
        re.compile(r"合同(?:金额|额).*?\d+.*?万"),
    ),

    # --- Legal & compliance ---
    _ClausePattern(
        "LEGAL_NO_BLACKLIST",
        "legal_compliance",
        RiskLevel.FATAL,
        ("失信被执行人", "黑名单", "行贿犯罪"),
    ),
    _ClausePattern(
        "LEGAL_NO_LITIGATION",
        "legal_compliance",
        RiskLevel.HIGH,
        ("重大诉讼", "仲裁", "行政处罚"),
    ),
)

class PowerDisqualificationScanner:
    """Scans tender text for power engineering disqualification clauses.

    Uses a three-layer matching strategy:
    1. Keyword presence detection
    2. Regex pattern matching for structured clauses
    3. Context analysis for risk grading (rejection vs advisory)
    """

    def __init__(
        self,
        patterns: tuple[_ClausePattern, ...] = _POWER_CLAUSE_PATTERNS,
    ) -> None:
        self._patterns = patterns

    def scan(self, text: str) -> list[PowerScanHit]:
        """Scan text for disqualification clauses.

        Returns list of PowerScanHit, empty if no clauses found.
        """
        if not text or not text.strip():
            return []

        hits: list[PowerScanHit] = []
        seen_patterns: set[str] = set()

        for pattern in self._patterns:
            hit = self._match_pattern(text, pattern)
            if hit is not None and pattern.pattern_id not in seen_patterns:
                seen_patterns.add(pattern.pattern_id)
                hits.append(hit)

        return hits

    def _match_pattern(
        self, text: str, pattern: _ClausePattern,
    ) -> PowerScanHit | None:
        """Try to match a single pattern against text."""
        # Layer 1: keyword presence
        keyword_offset = self._find_keyword(text, pattern.keywords)
        if keyword_offset < 0:
            return None

        # Layer 2: regex refinement (if available)
        matched_text = self._extract_clause_context(text, keyword_offset)
        if pattern.regex is not None:
            m = pattern.regex.search(text)
            if m:
                matched_text = m.group(0)
                keyword_offset = m.start()

        # Layer 3: context-based risk grading
        risk = self._grade_risk(text, keyword_offset, pattern.risk_level)

        return PowerScanHit(
            clause_text=matched_text[:300],
            risk_level=risk,
            category=pattern.category,
            source_offset=keyword_offset,
            pattern_id=pattern.pattern_id,
        )

    @staticmethod
    def _find_keyword(text: str, keywords: tuple[str, ...]) -> int:
        """Return offset of first keyword found, or -1."""
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                return idx
        return -1

    @staticmethod
    def _extract_clause_context(text: str, offset: int, window: int = 60) -> str:
        """Extract surrounding context around the matched offset."""
        start = max(0, offset - window)
        end = min(len(text), offset + window)
        return text[start:end].strip()

    @staticmethod
    def _grade_risk(
        text: str,
        offset: int,
        default_risk: RiskLevel,
    ) -> str:
        """Adjust risk level based on surrounding context."""
        # Look at a window around the match
        start = max(0, offset - 100)
        end = min(len(text), offset + 200)
        context = text[start:end]

        # If advisory markers present, downgrade to WARN
        for marker in _ADVISORY_MARKERS:
            if marker in context:
                return RiskLevel.WARN

        # If rejection markers present, upgrade to FATAL
        for marker in _REJECTION_MARKERS:
            if marker in context:
                return RiskLevel.FATAL

        return default_risk


# ── Main gate function ───────────────────────────────────────


def check_fatal_gate(
    prelim_data: dict,
    personnel_data: dict,
) -> FatalGateReport:
    """Check preliminary items against available assets.

    Also runs the power disqualification scanner on all clause texts
    to identify industry-specific rejection risks.
    """
    checks: list[FatalCheckResult] = []
    blocked_reasons: list[str] = []
    scanner = PowerDisqualificationScanner()
    all_scan_hits: list[PowerScanHit] = []

    for item in prelim_data.get("items", []):
        if not item.get("fatal_if_unmet", False):
            continue

        clause = item.get("clause_text", "")
        item_id = item.get("item_id", "unknown")

        matched, detail = _match_prelim_to_assets(clause)

        # Scan clause for power-specific risks
        scan_hits = scanner.scan(clause)
        all_scan_hits.extend(scan_hits)

        risk_level = RiskLevel.WARN
        category = "general"
        if scan_hits:
            risk_level = scan_hits[0].risk_level
            category = scan_hits[0].category

        checks.append(FatalCheckResult(
            item_id=item_id,
            clause_text=clause[:300],
            asset_matched=matched,
            match_detail=detail,
            blocked=not matched,
            risk_level=risk_level,
            category=category,
        ))

        if not matched:
            blocked_reasons.append(f"{item_id}: {clause[:100]}")

    for constraint in personnel_data.get("constraints", []):
        role = constraint.get("role", "unknown")
        matched, detail = _match_personnel_to_assets(constraint)

        checks.append(FatalCheckResult(
            item_id=f"PERSON-{role}",
            clause_text=f"人员要求: {role} — {constraint.get('cert_required', 'N/A')}",
            asset_matched=matched,
            match_detail=detail,
            blocked=not matched,
            risk_level=RiskLevel.HIGH,
            category="personnel",
        ))

        if not matched and constraint.get("cert_required"):
            blocked_reasons.append(
                f"人员缺失: {role} ({constraint.get('cert_required', '')})",
            )

    passed = len(blocked_reasons) == 0
    logger.info(
        "fatal gate: passed=%s, %d checks, %d blocked, %d power scan hits",
        passed, len(checks), len(blocked_reasons), len(all_scan_hits),
    )

    return FatalGateReport(
        passed=passed,
        blocked_reasons=blocked_reasons,
        checks=checks,
        power_scan_results=all_scan_hits,
    )


# ── Asset matching helpers ───────────────────────────────────


def _match_prelim_to_assets(clause_text: str) -> tuple[bool, str]:
    """Try to match a preliminary clause against company qualification assets."""
    try:
        from app.tender.assets.repository import get_company_qualifications

        qualifications = get_company_qualifications()
        if not qualifications:
            return False, "no company qualifications found in asset library"

        for qual in qualifications:
            title = (qual.get("title") or "").lower()
            if not title:
                continue
            clause_lower = clause_text.lower()
            keywords = ["资质", "许可", "证书", "营业执照", "安全生产"]
            for kw in keywords:
                if kw in clause_lower and kw in title:
                    return True, f"matched qualification: {qual.get('title')}"

        return True, "qualifications exist but exact match needs human review"
    except Exception as exc:  # noqa: BLE001
        logger.warning("asset query failed, defaulting to pass: %s", exc)
        return True, f"asset query error (defaulting to pass): {exc}"


def _match_personnel_to_assets(constraint: dict) -> tuple[bool, str]:
    """Try to match a personnel constraint against personnel assets."""
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
