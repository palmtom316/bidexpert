"""Task 15: pricing_guard 回归矩阵 (R24).

Regression matrix ensuring pricing guard correctly blocks/allows various inputs.
"""
from __future__ import annotations

import pytest

from app.services.pricing_guard import detect_pricing_content


SHOULD_BLOCK = [
    ("单价：钢筋 4500元/吨，混凝土 380元/m³，模板 45元/m²", "explicit unit prices"),
    ("投标报价：总价 12,500,000.00 元", "total bid price"),
    ("综合单价分析表：土方开挖 单价35.00元/m³ 合价175000元，钢筋制安 单价4500元/吨 合价900000元", "pricing table with units"),
]

SHOULD_NOT_BLOCK = [
    ("本工程采用C30混凝土，钢筋采用HRB400级", "technical spec no pricing"),
    ("施工现场配备50t履带吊1台，25t汽车吊2台", "equipment list"),
    ("项目经理具备一级建造师资格，从业经验15年以上", "personnel qualification"),
    ("工期要求180日历天，质量标准为合格", "schedule and quality"),
    ("安全生产许可证编号：(京)JZ安许证字[2024]001234号", "safety cert number"),
]


@pytest.mark.parametrize("text,desc", SHOULD_BLOCK, ids=[s[1] for s in SHOULD_BLOCK])
def test_pricing_guard_blocks(text: str, desc: str) -> None:
    blocked, reasons = detect_pricing_content(text)
    assert blocked, f"Expected blocked for: {desc}"


@pytest.mark.parametrize("text,desc", SHOULD_NOT_BLOCK, ids=[s[1] for s in SHOULD_NOT_BLOCK])
def test_pricing_guard_allows(text: str, desc: str) -> None:
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Unexpected block for: {desc}. Reasons: {reasons}"
