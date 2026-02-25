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
PRICING_CONTEXT_KEYWORDS = {
    "单价", "合计", "总价", "金额", "报价", "费用", "造价", "预算", "结算",
    "措施费", "安措费", "调试费", "检测费", "监理费",
    "设计费", "勘察费", "临时用电费", "大型机具费",
}

POWER_UNIT_WHITELIST = {
    "kV", "KV", "kv", "MVA", "MW", "kW", "kVA",
    "kA", "A", "V", "Hz", "mm²", "mm2",
    "m/s", "℃", "Ω", "MΩ",
}

POWER_TECH_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:kV|KV|kv|MVA|MW|kW|kVA|kA|Hz|mm²|mm2|m/s|℃|Ω|MΩ)"
)

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


def _strip_power_tech_numbers(text: str) -> str:
    """Remove power engineering technical parameter numbers before digit density calculation."""
    return POWER_TECH_PATTERN.sub("", text)


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


# Non-pricing Chinese words containing 元 — used to avoid false positives
_YUAN_FALSE_POSITIVE_WORDS = {"元件", "元素", "单元", "元旦", "元器件", "元年", "多元", "元数据"}

# Section title keywords that indicate technical (non-pricing) content
_TECHNICAL_SECTION_KEYWORDS = (
    "施工方案", "施工组织", "安全施工", "安全方案", "安全管理", "安全生产",
    "质量保证", "质量管理", "质量控制", "质量体系",
    "环境保护", "环保方案", "水土保持",
    "进度计划", "工期保证", "资源配置",
    "技术方案", "技术路线", "调试方案", "带电作业",
    "应急预案", "文明施工", "职业健康",
)


def _is_technical_context(text: str) -> bool:
    """Check if text appears to be a technical section (not pricing)."""
    first_200 = text[:200]
    return any(kw in first_200 for kw in _TECHNICAL_SECTION_KEYWORDS)


def _filter_yuan_false_positives(text: str, keyword: str) -> bool:
    """Return True if keyword '元' is actually part of a non-monetary word."""
    if keyword != "元":
        return False
    for word in _YUAN_FALSE_POSITIVE_WORDS:
        if word in text:
            return True
    return False


def detect_pricing_content(text: str) -> tuple[bool, list[str]]:
    signals: list[str] = []
    is_technical = _is_technical_context(text)

    # Signal 1: hard keyword match (always blocks alone)
    hard_hits = sorted([kw for kw in ALWAYS_BLOCK_KEYWORDS if kw in text])
    if hard_hits:
        signals.append(f"关键词命中(高风险): {', '.join(hard_hits)}")
        # Hard keywords block immediately — no 2-signal requirement
        return (True, signals)

    # Signal 2: context keyword + monetary amount nearby
    matched_keywords: list[str] = []
    for kw in CONTEXT_KEYWORDS:
        if kw not in text:
            continue
        if _filter_yuan_false_positives(text, kw):
            continue
        for match in re.finditer(re.escape(kw), text):
            if _has_amount_context(text, match.start(), match.end()):
                matched_keywords.append(kw)
                break
    if matched_keywords:
        signals.append(f"关键词命中(含金额上下文): {', '.join(sorted(set(matched_keywords)))}")

    # Signal 3: currency amount + pricing context keyword
    amount_hits = AMOUNT_PATTERN.findall(text)
    has_pricing_context = any(kw in text for kw in PRICING_CONTEXT_KEYWORDS)
    if amount_hits and has_pricing_context:
        signals.append("发现货币符号/货币代码与金额数字")

    # Signal 4: high digit density
    stripped_text = _strip_power_tech_numbers(text)
    numbers = NUMBER_PATTERN.findall(stripped_text)
    token_count = _estimate_token_count(text)
    digit_density = len(numbers) / token_count
    if len(numbers) >= 10 and digit_density > 0.3:
        signals.append("疑似金额/报价表结构（高数字密度）")

    # Require 2+ signals to block (reduced to 1+ if NOT technical context
    # and signal is strong — i.e. Signal 2 with multiple keywords)
    if is_technical:
        # Technical sections need 3+ signals to block
        blocked = len(signals) >= 3
    else:
        # Non-technical: 2+ signals required
        blocked = len(signals) >= 2

    return (blocked, signals)
