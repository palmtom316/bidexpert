"""Tests for power engineering disqualification clause identification.

TDD RED phase — these tests define the expected behavior of the
enhanced fatal_gate module for power engineering bidding documents.
"""

from __future__ import annotations

import pytest

from app.tender.fatal_gate import (
    PowerDisqualificationScanner,
    RiskLevel,
    check_fatal_gate,
)
from app.tender.schemas import FatalCheckResult, FatalGateReport


# ── Risk level enum ──────────────────────────────────────────


class TestRiskLevel:
    def test_risk_levels_exist(self):
        assert RiskLevel.FATAL == "FATAL"
        assert RiskLevel.HIGH == "HIGH"
        assert RiskLevel.WARN == "WARN"


# ── PowerDisqualificationScanner ─────────────────────────────


class TestPowerDisqualificationScanner:
    """Test the new scanner that identifies power-industry disqualification
    clauses from raw tender text."""

    @pytest.fixture()
    def scanner(self) -> PowerDisqualificationScanner:
        return PowerDisqualificationScanner()

    # -- Qualification & license clauses --

    def test_detects_safety_production_license(self, scanner):
        text = "投标人须具有有效的安全生产许可证，否则按废标处理。"
        results = scanner.scan(text)
        assert len(results) >= 1
        hit = results[0]
        assert hit.risk_level == RiskLevel.FATAL
        assert "安全生产许可证" in hit.clause_text

    def test_detects_electrical_qualification_grade(self, scanner):
        text = "投标人须具备电力工程施工总承包壹级及以上资质。不满足资质要求的投标文件将被否决。"
        results = scanner.scan(text)
        assert len(results) >= 1
        assert any(r.risk_level == RiskLevel.FATAL for r in results)

    def test_detects_special_operator_cert(self, scanner):
        text = "项目经理须持有一级建造师（机电工程或电力工程）注册证书，特种作业人员须持有电工作业、高处作业操作证。"
        results = scanner.scan(text)
        assert len(results) >= 1
        assert any("特种作业" in r.clause_text or "操作证" in r.clause_text for r in results)

    # -- Bid bond & procedural clauses --

    def test_detects_bid_bond_requirement(self, scanner):
        text = "投标保证金人民币50万元整，须在投标截止时间前到达指定账户，否则投标无效。"
        results = scanner.scan(text)
        assert len(results) >= 1
        assert any(r.risk_level == RiskLevel.FATAL for r in results)

    def test_detects_bid_validity_period(self, scanner):
        text = "投标有效期为90天，自投标截止日起算。投标有效期不足的投标将被拒绝。"
        results = scanner.scan(text)
        assert len(results) >= 1

    # -- Power-industry-specific clauses --

    def test_detects_voltage_level_requirement(self, scanner):
        text = "投标人近五年内须有110kV及以上电压等级输变电工程施工业绩，否则不予通过资格审查。"
        results = scanner.scan(text)
        assert len(results) >= 1
        assert any(r.category == "voltage_performance" or "电压等级" in r.clause_text for r in results)

    def test_detects_grid_connection_acceptance(self, scanner):
        text = "中标人须配合完成并网验收，未通过并网验收的不予结算。"
        results = scanner.scan(text)
        assert len(results) >= 1

    def test_detects_relay_protection_requirement(self, scanner):
        text = "投标人须提供继电保护整定计算方案及调试人员资质证明。"
        results = scanner.scan(text)
        assert len(results) >= 1

    def test_detects_live_work_qualification(self, scanner):
        text = "涉及带电作业的，投标人须具备带电作业资质及相应安全工器具检测报告。"
        results = scanner.scan(text)
        assert len(results) >= 1
        assert any(r.risk_level in (RiskLevel.FATAL, RiskLevel.HIGH) for r in results)

    def test_detects_power_facility_protection_zone(self, scanner):
        text = "施工范围涉及电力设施保护区的，须取得电力管理部门批准文件。"
        results = scanner.scan(text)
        assert len(results) >= 1

    # -- Negative cases --

    def test_no_false_positive_on_generic_text(self, scanner):
        text = "本工程位于某市经济开发区，建筑面积约5000平方米，结构形式为框架结构。"
        results = scanner.scan(text)
        assert len(results) == 0

    def test_no_false_positive_on_technical_description(self, scanner):
        text = "采用预应力混凝土管桩基础，桩径400mm，桩长12m，单桩承载力特征值800kN。"
        results = scanner.scan(text)
        assert len(results) == 0

    # -- Risk grading --

    def test_fatal_risk_for_mandatory_rejection(self, scanner):
        text = "未提供安全生产许可证的投标文件将被否决。"
        results = scanner.scan(text)
        assert all(r.risk_level == RiskLevel.FATAL for r in results)

    def test_high_risk_for_conditional_clause(self, scanner):
        text = "投标人宜具有类似工程施工经验，缺乏经验的将酌情扣分。"
        results = scanner.scan(text)
        # This is a scoring clause, not a disqualification — should be WARN at most
        fatal_hits = [r for r in results if r.risk_level == RiskLevel.FATAL]
        assert len(fatal_hits) == 0

    # -- Report structure --

    def test_scan_returns_structured_results(self, scanner):
        text = "投标人须具有安全生产许可证，须缴纳投标保证金50万元。"
        results = scanner.scan(text)
        for r in results:
            assert hasattr(r, "clause_text")
            assert hasattr(r, "risk_level")
            assert hasattr(r, "category")
            assert hasattr(r, "source_offset")
            assert r.risk_level in (RiskLevel.FATAL, RiskLevel.HIGH, RiskLevel.WARN)

    # -- Batch scanning --

    def test_scan_multiple_sections(self, scanner):
        sections = [
            "第一章 投标须知：投标人须具有电力工程施工总承包资质。",
            "第二章 技术要求：本工程电压等级为220kV。",
            "第三章 评标办法：未提供安全生产许可证的按废标处理。",
        ]
        all_results = []
        for section in sections:
            all_results.extend(scanner.scan(section))
        assert len(all_results) >= 2


# ── Integration with check_fatal_gate ────────────────────────


class TestCheckFatalGateWithPowerClauses:
    """Verify that the enhanced check_fatal_gate function integrates
    the power disqualification scanner results."""

    def test_report_includes_risk_level(self):
        prelim_data = {
            "items": [
                {
                    "item_id": "P-001",
                    "clause_text": "投标人须具有安全生产许可证",
                    "fatal_if_unmet": True,
                },
            ],
        }
        report = check_fatal_gate(prelim_data, {"constraints": []})
        assert isinstance(report, FatalGateReport)
        # The check results should now include risk_level
        for check in report.checks:
            assert hasattr(check, "risk_level")

    def test_report_includes_category(self):
        prelim_data = {
            "items": [
                {
                    "item_id": "P-002",
                    "clause_text": "投标保证金须在截止时间前到账",
                    "fatal_if_unmet": True,
                },
            ],
        }
        report = check_fatal_gate(prelim_data, {"constraints": []})
        for check in report.checks:
            assert hasattr(check, "category")
