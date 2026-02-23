from __future__ import annotations

from app.services.pricing_guard import detect_pricing_content


def test_pricing_guard_regression_matrix() -> None:
    matrix = [
        {
            "text": "本章仅描述技术参数：主变容量 50MVA，额定电压 110kV，RMB 仅用于单位说明，不涉及报价。",
            "blocked": False,
        },
        {
            "text": "投标报价总价为人民币 1200000 元，单价明细见附件。",
            "blocked": True,
        },
        {
            "text": "服务费按月结算，含税金额 12.5 万元。",
            "blocked": True,
        },
        {
            "text": "无金额、无报价，仅提供施工工艺和进度节点。",
            "blocked": False,
        },
    ]

    for case in matrix:
        blocked, _reasons = detect_pricing_content(case["text"])
        assert blocked is case["blocked"], case["text"]
