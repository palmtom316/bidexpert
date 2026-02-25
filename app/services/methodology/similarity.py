from __future__ import annotations

from app.services.methodology.types import SimilarityAssessment


def _normalize(text: str) -> str:
    return "".join(str(text or "").split())


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def evaluate_similarity(*, source_text: str, rewritten_text: str, threshold: float = 0.35) -> SimilarityAssessment:
    source = _normalize(source_text)
    rewritten = _normalize(rewritten_text)

    source_grams = _char_ngrams(source, 3)
    rewritten_grams = _char_ngrams(rewritten, 3)
    if not source_grams:
        score = 0.0
    else:
        overlap = source_grams & rewritten_grams
        score = len(overlap) / len(source_grams)

    decision = "need_edit" if score > threshold else "pass"
    return SimilarityAssessment(score=score, threshold=threshold, decision=decision)
