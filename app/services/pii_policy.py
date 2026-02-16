from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pricing_guard import detect_pricing_content

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])"
)
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
ID_CARD_PATTERN = re.compile(r"\b\d{17}[\dXx]\b")
TECH_PARAM_PATTERN = re.compile(
    r"([A-Za-z\u4e00-\u9fff]{1,12}\s*[:：]?\s*\d+(?:\.\d+)?\s*(?:ms|s|GB|TB|MB/s|Gbps|%|QPS|TPS|MHz|kW|℃)?)"
)


@dataclass
class SanitizeResult:
    text: str
    pricing_blocked: bool
    warnings: list[str]


def _mask_pii(text: str) -> str:
    masked = EMAIL_PATTERN.sub("***@***", text)
    masked = PHONE_PATTERN.sub("***********", masked)
    masked = ID_CARD_PATTERN.sub("******************", masked)
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
