from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

SENTENCE_SPLIT = re.compile(r"[。；;!?！？\n]+")
MUST_PATTERN = re.compile(r"(必须|应当|不得|需|须|满足)")


@dataclass
class GateResult:
    status: str
    missing_sentences: list[str]
    coverage: float


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _extract_fact_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if len(s.strip()) >= 8]


def gate1_evidence_binding(evidence_ids: list[str]) -> bool:
    return len(evidence_ids) > 0


def gate2_deterministic_check(generated_text: str, evidence_texts: list[str]) -> list[str]:
    evidence_pool = [_normalize(x) for x in evidence_texts]
    missing: list[str] = []
    for sentence in _extract_fact_sentences(generated_text):
        norm_sentence = _normalize(sentence)
        matched = False
        for ev in evidence_pool:
            if norm_sentence in ev:
                matched = True
                break
            if fuzz.partial_ratio(norm_sentence, ev) >= 88:
                matched = True
                break
        if not matched:
            missing.append(sentence)
    return missing


def gate3_matrix_coverage(requirement_mapped: int, requirement_total: int) -> float:
    if requirement_total <= 0:
        return 0.0
    return requirement_mapped / requirement_total


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

    coverage = gate3_matrix_coverage(requirement_mapped, requirement_total)
    if coverage < coverage_threshold:
        return GateResult("NEED_HUMAN_INPUT", ["coverage_below_threshold"], coverage)
    if requirement_text and MUST_PATTERN.search(requirement_text) and coverage < 1.0:
        return GateResult("NEED_HUMAN_INPUT", ["must_clause_coverage_insufficient"], coverage)

    return GateResult("SUPPORTED", [], coverage)
