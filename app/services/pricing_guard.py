from __future__ import annotations

import re

ALWAYS_BLOCK_KEYWORDS = {
    "投标报价",
    "报价表",
}

CONTEXT_KEYWORDS = {
    "报价",
    "单价",
    "总价",
    "合计",
    "金额",
    "费用",
    "税率",
    "含税",
    "不含税",
}

CURRENCY_PATTERN = re.compile(r"(?:¥|RMB|USD|CNY|\$|人民币|元)")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+(?:\.\d+)?")
CONTEXT_WINDOW = 20
SAFE_NEGATION_PHRASES = (
    "不涉及报价",
    "不涉及金额",
    "不包含报价",
    "不包含金额",
    "无报价",
    "无金额",
)


def _context_slice(text: str, start: int, end: int) -> str:
    left = max(0, start - CONTEXT_WINDOW)
    right = min(len(text), end + CONTEXT_WINDOW)
    return text[left:right]


def _has_safe_negation(context: str) -> bool:
    return any(phrase in context for phrase in SAFE_NEGATION_PHRASES)


def _has_pricing_semantics(context: str) -> bool:
    if _has_safe_negation(context):
        return False
    return any(kw in context for kw in CONTEXT_KEYWORDS)


def _has_amount_context(text: str, start: int, end: int) -> bool:
    context = _context_slice(text, start, end)
    has_number = bool(NUMBER_PATTERN.search(context))
    has_currency = bool(CURRENCY_PATTERN.search(context))
    return has_number and (has_currency or _has_pricing_semantics(context))


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
            context = _context_slice(text, match.start(), match.end())
            if _has_safe_negation(context):
                continue
            if _has_amount_context(text, match.start(), match.end()):
                matched_keywords.append(kw)
                break
    if matched_keywords:
        reasons.append(f"关键词命中(含金额上下文): {', '.join(sorted(set(matched_keywords)))}")

    currency_context_hits = 0
    for currency_match in CURRENCY_PATTERN.finditer(text):
        context = _context_slice(text, currency_match.start(), currency_match.end())
        if _has_pricing_semantics(context) and NUMBER_PATTERN.search(context):
            currency_context_hits += 1
    if currency_context_hits > 0:
        reasons.append("发现货币符号/货币代码与报价语义上下文")

    numbers = NUMBER_PATTERN.findall(text)
    token_count = len(TOKEN_PATTERN.findall(text))
    digit_density = len(numbers) / max(len(text.split()), 1)
    if token_count > 0:
        digit_density = len(numbers) / token_count
    if len(numbers) >= 10 and digit_density > 0.3 and _has_pricing_semantics(text):
        reasons.append("疑似金额/报价表结构（高数字密度）")

    return (len(reasons) > 0, reasons)
