from __future__ import annotations

import re

from app.services.methodology.types import SanitizeResult

_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_PATTERN = re.compile(r"\b\d{17}[\dXx]\b")
_COMPANY_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:有限公司|集团|项目部|工程公司)")
_CONTRACT_NO_PATTERN = re.compile(r"(?:合同号|合同编号)[:：]?\s*[A-Za-z0-9-]{4,}")
_MONEY_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:万元|元|人民币|万)\b")


def _mask(pattern: re.Pattern[str], text: str, replacement: str, finding_type: str, findings: list[dict]) -> str:
    matches = list(pattern.finditer(text))
    if not matches:
        return text
    for match in matches:
        findings.append({"type": finding_type, "value": match.group(0)})
    return pattern.sub(replacement, text)


def remove_pii(raw_text: str) -> SanitizeResult:
    text = raw_text or ""
    findings: list[dict] = []

    sanitized = _mask(_PHONE_PATTERN, text, "***********", "phone", findings)
    sanitized = _mask(_ID_PATTERN, sanitized, "******************", "id_card", findings)
    sanitized = _mask(_CONTRACT_NO_PATTERN, sanitized, "合同编号: [REDACTED]", "contract_no", findings)
    sanitized = _mask(_MONEY_PATTERN, sanitized, "[REDACTED_AMOUNT]", "amount", findings)
    sanitized = _mask(_COMPANY_PATTERN, sanitized, "[REDACTED_ORG]", "organization", findings)

    return SanitizeResult(
        sanitized_text=sanitized,
        pii_removed=True,
        findings=findings,
    )
