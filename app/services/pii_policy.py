from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pricing_guard import detect_pricing_content

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])"
)
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_PATTERN = re.compile(r"\b\d{17}[\dXx]\b")
TECH_PARAM_PATTERN = re.compile(
    r"([A-Za-z\u4e00-\u9fff]{1,12}\s*[:：]?\s*\d+(?:\.\d+)?\s*(?:ms|s|GB|TB|MB/s|Gbps|%|QPS|TPS|MHz|kW|℃)?)"
)

# Bid document personnel context — these names/certs should NOT be masked
_BID_PERSONNEL_CONTEXT = re.compile(
    r"(?:项目经理|项目负责人|技术负责人|安全员|质量员|施工员|"
    r"总工程师|副总工程师|专职安全员|总监理工程师|"
    r"注册建造师|注册监理工程师|注册造价工程师|注册电气工程师)"
)

# Enterprise credential patterns — should NOT be masked
_ENTERPRISE_CREDENTIAL = re.compile(
    r"(?:统一社会信用代码|营业执照编号|资质证书编号|"
    r"安全生产许可证编号|承装修试许可证编号|"
    r"电力业务许可证编号|施工许可证号)"
)

_CREDENTIAL_NUMBER = re.compile(
    r"(?:统一社会信用代码|营业执照编号|资质证书编号|"
    r"安全生产许可证编号|承装修试许可证编号|"
    r"电力业务许可证编号|施工许可证号)"
    r"[:：]\s*([A-Za-z0-9\-]{6,30})"
)


@dataclass
class SanitizeResult:
    text: str
    pricing_blocked: bool
    warnings: list[str]


_ID_CARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CARD_CHECKSUM_MAP = "10X98765432"


def _is_valid_id_card(candidate: str) -> bool:
    if len(candidate) != 18 or not candidate[:17].isdigit():
        return False
    checksum = sum(int(digit) * weight for digit, weight in zip(candidate[:17], _ID_CARD_WEIGHTS, strict=True)) % 11
    expected = _ID_CARD_CHECKSUM_MAP[checksum]
    return candidate[-1].upper() == expected


def _mask_id_cards(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        return "******************" if _is_valid_id_card(token) else token

    return ID_CARD_PATTERN.sub(replace, text)


def _is_bid_personnel_context(text: str, match_start: int, window: int = 60) -> bool:
    """Check if a PII match is within a bid personnel context (should be preserved)."""
    left = max(0, match_start - window)
    context = text[left:match_start + window]
    return bool(_BID_PERSONNEL_CONTEXT.search(context))


def _is_enterprise_credential(text: str, match_start: int, window: int = 60) -> bool:
    """Check if a number match is an enterprise credential (should be preserved)."""
    left = max(0, match_start - window)
    context = text[left:match_start + window]
    return bool(_ENTERPRISE_CREDENTIAL.search(context))


def _mask_pii(text: str) -> str:
    # Preserve emails in bid personnel context
    def _email_replace(match: re.Match[str]) -> str:
        if _is_bid_personnel_context(text, match.start()):
            return match.group(0)
        return "***@***"

    # Preserve phones in bid personnel context
    def _phone_replace(match: re.Match[str]) -> str:
        if _is_bid_personnel_context(text, match.start()):
            return match.group(0)
        return "***********"

    masked = EMAIL_PATTERN.sub(_email_replace, text)
    masked = PHONE_PATTERN.sub(_phone_replace, masked)
    masked = _mask_id_cards(masked)
    return masked


def _apply_sensitive_strategy(text: str, strategy: str, allowlist: list[str] | None = None) -> str:
    allowlist = allowlist or []

    def replace(match: re.Match[str]) -> str:
        segment = match.group(1)
        if strategy == "allowlist":
            if any(token in segment for token in allowlist):
                return segment
            return re.sub(r"\d+(?:\.\d+)?", "***", segment)
        if strategy == "local_fill":
            return "[LOCAL_FILL_REQUIRED]"
        return re.sub(r"\d+(?:\.\d+)?", "***", segment)

    return TECH_PARAM_PATTERN.sub(replace, text)


def sanitize_outbound_text(
    text: str,
    sensitive_strategy: str = "mask",
    allowlist: list[str] | None = None,
) -> SanitizeResult:
    warnings: list[str] = []

    blocked, reasons = detect_pricing_content(text)
    if blocked:
        warnings.extend([f"pricing_blocked:{reason}" for reason in reasons])
        return SanitizeResult(text="BLOCKED_PRICING_CONTENT", pricing_blocked=True, warnings=warnings)

    sanitized = _mask_pii(text)
    if sanitized != text:
        warnings.append("pii_masked")

    sanitized2 = _apply_sensitive_strategy(sanitized, sensitive_strategy, allowlist)
    if sanitized2 != sanitized:
        warnings.append(f"sensitive_strategy_applied:{sensitive_strategy}")

    return SanitizeResult(text=sanitized2, pricing_blocked=False, warnings=warnings)


def sanitize_inbound_text(text: str) -> SanitizeResult:
    warnings: list[str] = []

    blocked, reasons = detect_pricing_content(text)
    if blocked:
        warnings.extend([f"pricing_blocked:{reason}" for reason in reasons])
        return SanitizeResult(text="BLOCKED_PRICING_CONTENT", pricing_blocked=True, warnings=warnings)

    sanitized = _mask_pii(text)
    if sanitized != text:
        warnings.append("pii_masked_inbound")

    return SanitizeResult(text=sanitized, pricing_blocked=False, warnings=warnings)
