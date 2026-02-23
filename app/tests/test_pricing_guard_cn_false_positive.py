from __future__ import annotations

from app.services.pricing_guard import detect_pricing_content


def test_cn_dense_technical_text_does_not_trigger_high_digit_density_block() -> None:
    text = (
        "技术参数如下电压220V频率50Hz功率30kW电流100A温度40C湿度60%"
        "长度1200mm宽度800mm高度1600mm重量300kg防护等级IP65通信速率9600bps"
    )
    blocked, reasons = detect_pricing_content(text)
    assert blocked is False
    assert not reasons


def test_cn_pricing_expression_with_amount_context_is_blocked() -> None:
    text = "报价清单：单价1000元数量10合计10000元税率13%总价11300元。"
    blocked, reasons = detect_pricing_content(text)
    assert blocked is True
    assert reasons
