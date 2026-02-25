"""Extract key personnel constraints (project manager, safety officer, etc.)."""

from __future__ import annotations

import logging
import re

from app.tender.schemas import KeyPersonnelConstraints, PersonnelConstraint

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")

# Role detection patterns
_ROLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("项目经理", re.compile(r"项目经理|项目负责人")),
    ("技术负责人", re.compile(r"技术负责人|技术总工|总工程师")),
    ("安全员", re.compile(r"安全员|安全负责人|专职安全[管生]")),
    ("质量员", re.compile(r"质量员|质量负责人|质检[员师]")),
    ("施工员", re.compile(r"施工员|现场负责")),
]

# Certificate patterns
_CERT_PATTERN = re.compile(
    r"(一级建造师|二级建造师|注册[电气安全造价监理]+工程师"
    r"|高级工程师|工程师|技师|高级技师"
    r"|安全生产考核合格证[书]?|[ABC]类安全证"
    r"|特种作业[操资][作质]证|电工[进资][网质]证"
    r"|承装修试[一二三四五]级)"
)

# Constraint patterns
_NO_ACTIVE = re.compile(r"无在建|不得.*在建|在建工程.*[为是].*[零0无]")
_SOCIAL_SECURITY = re.compile(r"社保\D{0,6}(\d+)\s*个?月")
_EXPERIENCE_YEARS = re.compile(r"(\d+)\s*年.*(?:工作经验|从业经[历验]|工程经验)")


def extract_key_personnel(markdown_text: str) -> KeyPersonnelConstraints:
    """Extract key personnel requirements from tender text."""
    constraints: list[PersonnelConstraint] = []
    seen_roles: set[str] = set()

    for raw in _SENTENCE_SPLIT.split(markdown_text):
        line = raw.strip()
        if len(line) < 10:
            continue

        for role_name, role_pat in _ROLE_PATTERNS:
            if not role_pat.search(line):
                continue

            cert_match = _CERT_PATTERN.search(line)
            no_active = bool(_NO_ACTIVE.search(line))
            ss_match = _SOCIAL_SECURITY.search(line)
            exp_match = _EXPERIENCE_YEARS.search(line)

            # Deduplicate by role — keep the richer one
            key = role_name
            if key in seen_roles:
                continue
            seen_roles.add(key)

            constraints.append(PersonnelConstraint(
                role=role_name,
                cert_required=cert_match.group(0) if cert_match else None,
                no_active_project=no_active,
                social_security_months=int(ss_match.group(1)) if ss_match else None,
                min_experience_years=int(exp_match.group(1)) if exp_match else None,
                source_clause=line[:300],
            ))

    logger.info("extracted %d personnel constraints", len(constraints))
    return KeyPersonnelConstraints(constraints=constraints)
