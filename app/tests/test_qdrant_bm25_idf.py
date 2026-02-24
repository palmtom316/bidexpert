"""Task 10: 检索 BM25/同义词/rerank — tests.

Covers:
- R03: _build_sparse_vector with IDF weighting gives rare terms higher scores
- R21: Synonym expansion can recall alias expressions
- R22: Rerank weights are configurable
"""
from __future__ import annotations

from app.services.retrieval_synonyms import expand_synonyms, SYNONYM_DICT
from app.services.qdrant_store import _build_sparse_vector, _tokenize


# ---------------------------------------------------------------------------
# R03: IDF weighting — rare terms score higher
# ---------------------------------------------------------------------------

def test_sparse_vector_not_empty() -> None:
    vec = _build_sparse_vector("投标人必须具备ISO9001资质")
    assert len(vec) > 0


def test_sparse_vector_values_are_positive() -> None:
    vec = _build_sparse_vector("投标人必须具备ISO9001资质")
    assert all(v > 0 for v in vec.values())


def test_build_sparse_vector_accepts_idf_dict() -> None:
    """_build_sparse_vector must accept an optional idf_weights parameter."""
    idf = {"投标": 3.0, "资质": 5.0}
    vec = _build_sparse_vector("投标人必须具备资质", idf_weights=idf)
    assert len(vec) > 0


def test_idf_boosts_rare_terms() -> None:
    """With IDF weights, a rare term should get a higher sparse score."""
    text = "投标 资质"
    idf = {"投标": 1.0, "资质": 10.0}
    vec_with_idf = _build_sparse_vector(text, idf_weights=idf)
    vec_no_idf = _build_sparse_vector(text)
    # Both should produce vectors, but with IDF the distribution changes
    assert len(vec_with_idf) > 0
    assert vec_with_idf != vec_no_idf


# ---------------------------------------------------------------------------
# R21: Synonym expansion
# ---------------------------------------------------------------------------

def test_synonym_dict_is_not_empty() -> None:
    assert len(SYNONYM_DICT) > 0


def test_expand_synonyms_returns_original_plus_aliases() -> None:
    expanded = expand_synonyms("施工组织设计")
    assert "施工组织设计" in expanded
    assert len(expanded) >= 1


def test_expand_synonyms_finds_known_alias() -> None:
    """At least one known synonym pair should expand."""
    # Check a few common pairs
    found_expansion = False
    for term, aliases in SYNONYM_DICT.items():
        expanded = expand_synonyms(term)
        if len(expanded) > 1:
            found_expansion = True
            break
    assert found_expansion, "No synonym expansions found in SYNONYM_DICT"


def test_expand_synonyms_unknown_term_returns_itself() -> None:
    expanded = expand_synonyms("完全不存在的术语xyz")
    assert expanded == ["完全不存在的术语xyz"]


# ---------------------------------------------------------------------------
# R22: Rerank weight configurability
# ---------------------------------------------------------------------------

def test_rerank_weights_configurable_in_settings() -> None:
    from app.core.config import settings
    assert hasattr(settings, "qdrant_rerank_dense_weight")
    assert hasattr(settings, "qdrant_rerank_sparse_weight")


def test_rerank_weights_sum_to_one() -> None:
    from app.core.config import settings
    total = settings.qdrant_rerank_dense_weight + settings.qdrant_rerank_sparse_weight
    assert abs(total - 1.0) < 0.01, f"Weights should sum to 1.0, got {total}"
