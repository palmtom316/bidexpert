from __future__ import annotations

import re

KEYWORDS = {
    "投标报价",
    "单价",
    "合计",
    "税率",
    "含税",
    "不含税",
    "RMB",
    "¥",
    "元",
    "报价表",
}

CURRENCY_PATTERN = re.compile(r"(?:¥|RMB|USD|CNY|\$)")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def detect_pricing_content(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    matched_keywords = [kw for kw in KEYWORDS if kw in text]
    if matched_keywords:
        reasons.append(f"关键词命中: {', '.join(sorted(matched_keywords))}")

    currency_hits = CURRENCY_PATTERN.findall(text)
    if currency_hits:
        reasons.append("发现货币符号/货币代码")

    numbers = NUMBER_PATTERN.findall(text)
    digit_density = len(numbers) / max(len(text.split()), 1)
    if len(numbers) >= 10 and digit_density > 0.3:
        reasons.append("疑似金额/报价表结构（高数字密度）")

    return (len(reasons) > 0, reasons)
