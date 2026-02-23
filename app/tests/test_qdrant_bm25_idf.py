from __future__ import annotations

from app.services.qdrant_store import (
    _build_sparse_token_weights,
    _register_sparse_documents_for_tests,
    _reset_sparse_stats_for_tests,
)
from app.services.retrieval_synonyms import expand_query_terms, expand_query_text


def test_bm25_idf_sparse_weight_boosts_low_frequency_terms() -> None:
    _reset_sparse_stats_for_tests()
    corpus = ["资质 要求 通用 条款"] * 30 + ["特高压 变电 设备 型号"] * 1
    _register_sparse_documents_for_tests(corpus)

    weights = _build_sparse_token_weights("资质 特高压")

    assert "资质" in weights
    assert "特高压" in weights
    assert weights["特高压"] > weights["资质"]


def test_query_synonym_expansion_supports_alias_recall() -> None:
    terms = expand_query_terms("投标人资质", max_expansions=6)
    assert any(item in terms for item in ("供应商", "竞标人", "资格"))

    expanded = expand_query_text("投标人资质", max_expansions=6)
    assert expanded.startswith("投标人资质")
    assert expanded != "投标人资质"
