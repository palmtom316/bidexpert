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
# Pattern for amounts that look like prices: currency symbol adjacent to a number
AMOUNT_PATTERN = re.compile(
    r"(?:¥|RMB|CNY)\s*\d+(?:[,，]\d{3})*(?:\.\d+)?|"
    r"\d+(?:[,，]\d{3})*(?:\.\d+)?\s*(?:元|万元)"
)
CONTEXT_WINDOW = 20

# Pricing-specific context keywords that distinguish real pricing from technical text
PRICING_CONTEXT_KEYWORDS = {"单价", "合计", "总价", "金额", "报价", "费用", "造价", "预算", "结算"}

# Pattern matching actual monetary amounts (not bare technical numbers)
MONETARY_NUMBER_PATTERN = re.compile(
    r"¥\s*\d|"
    r"\d+(?:[,，]\d{3})*(?:\.\d+)?\s*(?:元|万元)|"
    r"(?:RMB|CNY)\s*\d+(?:[,，]\d{3})*(?:\.\d+)?",
)


def _has_amount_context(text: str, start: int, end: int) -> bool:
    """Check if a keyword occurrence sits near an actual monetary amount,
    not just any bare number."""
    left = max(0, start - CONTEXT_WINDOW)
    right = min(len(text), end + CONTEXT_WINDOW)
    context = text[left:right]
    return bool(MONETARY_NUMBER_PATTERN.search(context))


def _estimate_token_count(text: str) -> int:
    """Estimate token count for mixed CJK/Latin text.

    For Chinese text without spaces, len(text.split()) returns ~1 which
    destroys digit density calculation. Instead, count CJK characters
    individually and split Latin/number runs by whitespace.
    """
    count = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            count += 1
        elif ch in (' ', '\t', '\n', '\r'):
            count += 1
        # Latin chars are counted as part of whitespace-delimited tokens
    # Add whitespace-delimited token count for non-CJK portions
    latin_tokens = len(re.findall(r'[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*', text))
    # Total: CJK chars + latin tokens, minimum 1
    cjk_count = sum(
        1 for ch in text
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf'
    )
    return max(cjk_count + latin_tokens, 1)


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

    # Signal 3 (fixed): require currency symbol adjacent to actual amount patterns
    # AND at least one pricing-context keyword nearby
    amount_hits = AMOUNT_PATTERN.findall(text)
    has_pricing_context = any(kw in text for kw in PRICING_CONTEXT_KEYWORDS)
    if amount_hits and has_pricing_context:
        reasons.append("发现货币符号/货币代码与金额数字")

    # Signal 4 (fixed): use CJK-aware token count instead of text.split()
    numbers = NUMBER_PATTERN.findall(text)
    token_count = _estimate_token_count(text)
    digit_density = len(numbers) / token_count
    if len(numbers) >= 10 and digit_density > 0.3:
        reasons.append("疑似金额/报价表结构（高数字密度）")

    return (len(reasons) > 0, reasons)
