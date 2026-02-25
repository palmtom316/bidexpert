"""Format & signature constraint extractor — regex-first approach (R1)."""

from __future__ import annotations

import logging
import re

from app.tender.schemas import FormatSignatureConstraints

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

# Paper copies: "正本X份" / "副本X份" / "X份"
_PAPER_COPIES = re.compile(r"正本\D{0,3}(\d+)\s*份")
_ELECTRONIC_COPIES = re.compile(r"电子[版本副]\D{0,3}(\d+)\s*[份套]|U盘\D{0,3}(\d+)\s*[份个套]")
_TOTAL_COPIES = re.compile(r"(?:共|合计|一式)\D{0,3}(\d+)\s*份")

# Binding
_BINDING_PATTERN = re.compile(r"(胶装|装订|活页|骑马钉|线装|精装|平装|密封)")

# Seal & signature
_SEAL_PATTERN = re.compile(
    r"(公章|法[人定]代表.*签[字章]|授权代表.*签[字章]|骑缝章|财务章|合同章"
    r"|投标专用章|电子签章|加盖.*章|盖章)"
)
_SIGNATURE_PAGE_PATTERN = re.compile(
    r"(签字盖章页|法定代表人.*页|授权委托书|开标一览表|投标函)"
)

# Envelope
_ENVELOPE_PATTERN = re.compile(
    r"(密封|封装|信封|外包装|标[书]?袋|技术标.*商务标.*分[开别]密封)"
)

# General format clause
_FORMAT_KEYWORDS = [
    "格式要求", "编排要求", "字体", "字号", "页码",
    "目录", "页眉", "页脚", "纸张", "A4", "A3",
    "份数", "装订", "密封",
]


def extract_format_signature(markdown_text: str) -> FormatSignatureConstraints:
    """Extract format, binding, seal, and envelope requirements via regex."""
    paper_copies: int | None = None
    electronic_copies: int | None = None
    binding_method: str | None = None
    seal_requirements: list[str] = []
    signature_pages: list[str] = []
    envelope_requirements: list[str] = []
    format_clauses: list[str] = []

    seen_seals: set[str] = set()
    seen_sigs: set[str] = set()
    seen_envelopes: set[str] = set()

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 6:
            continue

        # Paper copies
        if paper_copies is None:
            m = _PAPER_COPIES.search(line)
            if m:
                paper_copies = int(m.group(1))

        # Electronic copies
        if electronic_copies is None:
            m = _ELECTRONIC_COPIES.search(line)
            if m:
                electronic_copies = int(m.group(1) or m.group(2))

        # Total copies fallback
        if paper_copies is None:
            m = _TOTAL_COPIES.search(line)
            if m:
                paper_copies = int(m.group(1))

        # Binding
        if binding_method is None:
            m = _BINDING_PATTERN.search(line)
            if m:
                binding_method = m.group(1)

        # Seals
        for m in _SEAL_PATTERN.finditer(line):
            seal = m.group(0).strip()
            if seal not in seen_seals:
                seen_seals.add(seal)
                seal_requirements.append(f"{seal} — {line[:100]}")

        # Signature pages
        for m in _SIGNATURE_PAGE_PATTERN.finditer(line):
            sig = m.group(0).strip()
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                signature_pages.append(sig)

        # Envelopes
        for m in _ENVELOPE_PATTERN.finditer(line):
            env = m.group(0).strip()
            if env not in seen_envelopes:
                seen_envelopes.add(env)
                envelope_requirements.append(f"{env} — {line[:100]}")

        # General format clauses
        if any(k in line for k in _FORMAT_KEYWORDS):
            if len(format_clauses) < 20:
                format_clauses.append(line[:200])

    logger.info(
        "format/signature: copies=%s/%s, seals=%d, sigs=%d",
        paper_copies, electronic_copies, len(seal_requirements), len(signature_pages),
    )

    return FormatSignatureConstraints(
        paper_copies=paper_copies,
        electronic_copies=electronic_copies,
        binding_method=binding_method,
        seal_requirements=seal_requirements,
        signature_pages=signature_pages,
        envelope_requirements=envelope_requirements,
        format_clauses=format_clauses,
    )
