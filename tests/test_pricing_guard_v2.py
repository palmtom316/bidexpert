"""Tests for pricing guard v2 — require 2+ signals to block.

TDD RED phase: verifies that single-signal false positives are eliminated
while multi-signal real pricing content is still blocked.
"""
from __future__ import annotations


from app.services.pricing_guard import detect_pricing_content


class TestSingleSignalNoBlock:
    """A single signal alone should NOT block (except hard keywords)."""

    def test_technical_text_with_fee_mention(self):
        """费用 in technical context + no real amount → should NOT block."""
        text = "施工过程中应合理控制费用支出，做好成本管理工作，确保项目经济效益。"
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"technical fee mention should not block: {reasons}"

    def test_technical_text_with_yuan_unit(self):
        """元 as unit in technical context without pricing keywords → should NOT block."""
        text = "本工程采用高强度螺栓连接，每个元件重量约500kg，共计120个元件需要安装。"
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"元件 should not trigger: {reasons}"

    def test_schedule_with_many_numbers(self):
        """Schedule text with 10+ numbers but no pricing context → should NOT block."""
        text = (
            "第1阶段：基础施工30天，第2阶段：主体结构45天，第3阶段：设备安装60天，"
            "第4阶段：电气安装35天，第5阶段：调试15天，第6阶段：竣工验收10天。"
            "总工期195天，其中关键路径为第2和第3阶段共105天。"
            "投入人员高峰期达到150人，平均80人。施工机械12台套。"
        )
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"schedule with numbers should not block: {reasons}"

    def test_amount_pattern_in_narrative(self):
        """A casual monetary mention in narrative without pricing keywords → should NOT block."""
        text = "本项目总投资约3000万元，建设工期为18个月，预计2026年底投运。"
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"narrative investment mention should not block: {reasons}"


class TestMultiSignalBlocks:
    """Real pricing content with 2+ signals should still block."""

    def test_real_pricing_table(self):
        """Actual pricing table with amounts + pricing keywords → should block."""
        text = (
            "投标报价汇总表\n"
            "序号  项目名称  单价(元)  数量  合计(元)\n"
            "1  电缆敷设  ¥150.00  2000m  ¥300,000.00\n"
            "2  接地安装  ¥80.00   500m   ¥40,000.00\n"
            "总价合计: ¥340,000.00（含税）"
        )
        blocked, reasons = detect_pricing_content(text)
        assert blocked

    def test_unit_price_list(self):
        """Unit price list with 单价 + amounts → should block."""
        text = (
            "材料单价表：\n"
            "XLPE电缆 单价 85.50元/米\n"
            "绝缘子 单价 120.00元/个\n"
            "铁塔 单价 15000.00元/基\n"
            "合计金额: 2,500,000元"
        )
        blocked, reasons = detect_pricing_content(text)
        assert blocked

    def test_bid_total_with_tax(self):
        """Bid total with tax info → should block."""
        text = "投标报价总额为RMB 5,680,000.00元（含税），其中增值税税率为9%。"
        blocked, reasons = detect_pricing_content(text)
        assert blocked


class TestHardKeywordsStillBlock:
    """Hard block keywords should always block regardless of signal count."""

    def test_bid_pricing(self):
        blocked, _ = detect_pricing_content("投标报价说明")
        assert blocked

    def test_price_schedule(self):
        blocked, _ = detect_pricing_content("详见报价表")
        assert blocked


class TestTechnicalWhitelist:
    """Technical section types should have reduced sensitivity."""

    def test_safety_plan_with_cost_mention(self):
        """Safety plan mentioning costs should not be blocked."""
        text = (
            "安全施工方案\n"
            "安全防护费用应按照规定计取，不得低于工程造价的2%。"
            "安全生产措施费包括：临时用电费、安全防护设施费等。"
            "本工程安全文明施工费约50万元。"
        )
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"safety plan cost mention should not block: {reasons}"

    def test_quality_plan_with_testing_costs(self):
        """Quality plan mentioning testing costs should not be blocked."""
        text = (
            "质量保证体系\n"
            "检测费用由施工单位承担，每批次检测费约2000元。"
            "全部检测费用预计不超过10万元。"
        )
        blocked, reasons = detect_pricing_content(text)
        assert not blocked, f"quality plan testing cost should not block: {reasons}"
