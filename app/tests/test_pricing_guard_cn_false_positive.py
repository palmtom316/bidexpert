"""Task 2: pricing_guard 中文误报治理 — RED tests.

Covers R05:
- Signal 3: currency symbol + numbers in technical context should NOT block
- Signal 4: Chinese text without spaces should not inflate digit density
"""
from __future__ import annotations

from app.services.pricing_guard import detect_pricing_content


# ---------------------------------------------------------------------------
# Signal 3: RMB/¥ in technical context should not trigger
# ---------------------------------------------------------------------------

def test_rmb_with_technical_params_not_blocked() -> None:
    """Text mentioning RMB in a technical specification context (e.g. voltage,
    model numbers) should not be blocked when there's no actual pricing."""
    text = (
        "本项目采用RMB系列断路器，额定电压380V，额定电流630A，"
        "设备型号为RMB-630/3P，安装数量12台，防护等级IP54。"
    )
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Technical text with RMB model number should not be blocked: {reasons}"


def test_currency_symbol_in_unit_description_not_blocked() -> None:
    """A lone ¥ or $ in a unit/standard description without pricing table
    structure should not trigger blocking."""
    text = (
        "参照美国标准ASTM$D638进行拉伸试验，试样尺寸150mm×20mm×4mm，"
        "拉伸速度5mm/min，测试温度23℃，湿度50%RH。"
    )
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Technical text with $ in standard name should not be blocked: {reasons}"


def test_actual_pricing_table_still_blocked() -> None:
    """Real pricing content with currency + amounts in pricing context must
    still be blocked."""
    text = (
        "投标报价明细表\n"
        "序号  项目名称    单价(元)   数量   合计(元)\n"
        "1     钢筋加工    ¥350.00    100吨  ¥35000.00\n"
        "2     混凝土浇筑  ¥280.00    200m³  ¥56000.00\n"
        "合计金额：RMB 91000.00元"
    )
    blocked, reasons = detect_pricing_content(text)
    assert blocked, "Actual pricing table must still be blocked"


# ---------------------------------------------------------------------------
# Signal 4: Chinese text digit density must not be inflated by split()
# ---------------------------------------------------------------------------

def test_chinese_text_digit_density_not_inflated() -> None:
    """Dense Chinese text (no spaces) with scattered numbers should not
    trigger the high-density signal. text.split() on Chinese yields ~1 token,
    making density = num_count/1 which is always > 0.3."""
    text = (
        "本工程位于某市某区，建筑面积约15000平方米，地上18层，地下2层，"
        "建筑高度约56米，结构形式为框架剪力墙结构，抗震设防烈度7度，"
        "设计使用年限50年，耐火等级一级，防水等级二级。"
        "基础采用桩基础，桩径800mm，桩长约25米，共计120根。"
        "主体结构混凝土强度等级C30至C50，钢筋采用HRB400级。"
    )
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Chinese technical text should not trigger density signal: {reasons}"


def test_chinese_text_with_many_numbers_no_pricing() -> None:
    """Technical spec with 10+ numbers but no pricing semantics."""
    text = (
        "施工工期为365日历天，其中基础工程60天，主体结构180天，"
        "装饰装修90天，安装工程35天。质量目标：合格率100%，"
        "优良率95%以上。安全目标：重大事故为0，轻伤率控制在1.5‰以内。"
        "文明施工达标率100%，扬尘控制PM2.5浓度不超过75μg/m³。"
    )
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Technical schedule/quality text should not be blocked: {reasons}"
