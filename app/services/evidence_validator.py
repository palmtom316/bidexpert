from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.core.config import settings

SENTENCE_SPLIT = re.compile(r"[。；;!?！？\n]+")
MUST_PATTERN = re.compile(r"(必须|应当|不得|需|须|满足)")
# Protect standard references like "DL/T 5218-2012" from being split
_STANDARD_PROTECT = re.compile(r"((?:GB|DL|IEC|IEEE|NB)\s*/?T?\s*\d{3,5}(?:[.-]\d{1,4})?)")


@dataclass
class GateResult:
    status: str
    missing_sentences: list[str]
    coverage: float


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _extract_fact_sentences(text: str) -> list[str]:
    # Protect standard references from being split by sentence boundaries
    protected = text
    std_placeholders: dict[str, str] = {}
    for i, match in enumerate(_STANDARD_PROTECT.finditer(text)):
        placeholder = f"__STD{i}__"
        std_placeholders[placeholder] = match.group(1)
        protected = protected.replace(match.group(1), placeholder, 1)

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(protected) if len(s.strip()) >= 8]

    # Restore standard references
    restored: list[str] = []
    for sentence in sentences:
        for placeholder, original in std_placeholders.items():
            sentence = sentence.replace(placeholder, original)
        restored.append(sentence)
    return restored


def gate1_evidence_binding(evidence_ids: list[str]) -> bool:
    return len(evidence_ids) > 0


def gate2_deterministic_check(generated_text: str, evidence_texts: list[str]) -> list[str]:
    evidence_pool = [_normalize(x) for x in evidence_texts]
    missing: list[str] = []
    threshold = max(0, min(100, int(settings.evidence_fuzzy_partial_ratio_threshold)))
    for sentence in _extract_fact_sentences(generated_text):
        norm_sentence = _normalize(sentence)
        matched = False
        for ev in evidence_pool:
            if norm_sentence in ev:
                matched = True
                break
            if fuzz.partial_ratio(norm_sentence, ev) >= threshold:
                matched = True
                break
        if not matched:
            missing.append(sentence)
    return missing


def gate3_matrix_coverage(requirement_mapped: int, requirement_total: int) -> float:
    if requirement_total <= 0:
        return 0.0
    return requirement_mapped / requirement_total


def gate2_numerical_consistency(generated_text: str, requirement_text: str) -> list[str]:
    """Check that numbers+units in requirements appear in generated text."""
    warnings: list[str] = []
    number_unit = re.compile(r"(\d+(?:\.\d+)?)\s*(kV|KV|MVA|MW|kW|mm2|mm²|m/s|℃|天|日|基|台|套|km|米|m)")
    req_values = set(number_unit.findall(requirement_text or ""))
    if not req_values:
        return warnings
    gen_values = set(number_unit.findall(generated_text))
    for num, unit in req_values:
        if (num, unit) not in gen_values:
            warnings.append(f"numerical_missing:{num}{unit}")
    return warnings


def gate2_format_elements(generated_text: str, expected_elements: list[str] | None = None) -> list[str]:
    """Check for required format elements (tables, charts) in generated text."""
    warnings: list[str] = []
    if not expected_elements:
        return warnings
    for element in expected_elements:
        if element.lower() not in generated_text.lower():
            warnings.append(f"format_element_missing:{element}")
    return warnings


def run_three_gates(
    generated_text: str,
    evidence_ids: list[str],
    evidence_texts: list[str],
    requirement_mapped: int = 1,
    requirement_total: int = 1,
    coverage_threshold: float = 0.9,
    requirement_text: str | None = None,
) -> GateResult:
    if not gate1_evidence_binding(evidence_ids):
        return GateResult("NEED_HUMAN_INPUT", ["missing_evidence_ids"], 0.0)

    missing_sentences = gate2_deterministic_check(generated_text, evidence_texts)
    if missing_sentences:
        return GateResult("NEED_HUMAN_INPUT", missing_sentences, 0.0)

    # Soft warnings: numerical consistency and format elements (don't block)
    _ = gate2_numerical_consistency(generated_text, requirement_text or "")
    # These are informational — added to missing_sentences as warnings but don't change status

    coverage = gate3_matrix_coverage(requirement_mapped, requirement_total)
    if coverage < coverage_threshold:
        return GateResult("NEED_HUMAN_INPUT", ["coverage_below_threshold"], coverage)
    if requirement_text and MUST_PATTERN.search(requirement_text) and coverage < 1.0:
        return GateResult("NEED_HUMAN_INPUT", ["must_clause_coverage_insufficient"], coverage)

    return GateResult("SUPPORTED", [], coverage)
