from __future__ import annotations

import re

ALWAYS_BLOCK_KEYWORDS = {
    "投标报价",
    "报价表",
}

CONTEXT_KEYWORDS = {
    "单价",
    "合计",
    "税率",
    "含税",
    "不含税",
    "RMB",
    "¥",
    "元",
}

CURRENCY_PATTERN = re.compile(r"(?:¥|RMB|USD|CNY|\$)")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
CONTEXT_WINDOW = 20


def _has_amount_context(text: str, start: int, end: int) -> bool:
    left = max(0, start - CONTEXT_WINDOW)
    right = min(len(text), end + CONTEXT_WINDOW)
    context = text[left:right]
    return bool(CURRENCY_PATTERN.search(context) and NUMBER_PATTERN.search(context))


def detect_pricing_content(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    hard_hits = sorted([kw for kw in ALWAYS_BLOCK_KEYWORDS if kw in text])
    if hard_hits:
        reasons.append(f"关键词命中(高风险): {', '.join(hard_hits)}")

    matched_keywords: list[str] = []
    for kw in CONTEXT_KEYWORDS:
        if kw not in text:
            continue
        for match in re.finditer(re.escape(kw), text):
            if _has_amount_context(text, match.start(), match.end()):
                matched_keywords.append(kw)
                break
    if matched_keywords:
        reasons.append(f"关键词命中(含金额上下文): {', '.join(sorted(set(matched_keywords)))}")

    currency_hits = CURRENCY_PATTERN.findall(text)
    numbers = NUMBER_PATTERN.findall(text)
    if currency_hits and numbers:
        reasons.append("发现货币符号/货币代码与金额数字")

    digit_density = len(numbers) / max(len(text.split()), 1)
    if len(numbers) >= 10 and digit_density > 0.3:
        reasons.append("疑似金额/报价表结构（高数字密度）")

    return (len(reasons) > 0, reasons)
