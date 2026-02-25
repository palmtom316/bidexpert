"""Tests for search quality improvements — synonym wiring, score threshold, chunk length.

TDD RED phase.
"""
from __future__ import annotations

import pytest

from app.services.retrieval_synonyms import SYNONYM_DICT, expand_synonyms


class TestSynonymExpansion:
    """Verify power engineering synonyms are present."""

    def test_substation_synonyms(self):
        result = expand_synonyms("变电站")
        assert "变电所" in result

    def test_transmission_line_synonyms(self):
        result = expand_synonyms("架空线路")
        assert "输电线路" in result

    def test_cable_synonyms(self):
        result = expand_synonyms("电缆")
        assert "电力电缆" in result

    def test_relay_protection_synonyms(self):
        result = expand_synonyms("继电保护")
        assert "继保" in result

    def test_gis_synonyms(self):
        result = expand_synonyms("GIS")
        assert "气体绝缘开关" in result or "气体绝缘开关设备" in result

    def test_grounding_synonyms(self):
        result = expand_synonyms("接地")
        assert "接地装置" in result or "接地网" in result

    def test_bidirectional(self):
        """Synonyms should work in both directions."""
        result = expand_synonyms("变电所")
        assert "变电站" in result


class TestSynonymQueryExpansion:
    """Verify synonym expansion produces augmented query text."""

    def test_expand_query_with_synonyms(self):
        from app.services.qdrant_store import _expand_query_with_synonyms
        expanded = _expand_query_with_synonyms("变电站施工方案")
        assert "变电所" in expanded

    def test_no_expansion_for_unknown(self):
        from app.services.qdrant_store import _expand_query_with_synonyms
        original = "未知术语测试"
        expanded = _expand_query_with_synonyms(original)
        assert original in expanded


class TestMinScoreThreshold:
    """Verify low-score results are filtered out."""

    def test_score_threshold_config_exists(self):
        from app.core.config import settings
        assert hasattr(settings, "qdrant_min_score_threshold")
        assert settings.qdrant_min_score_threshold >= 0.0

    def test_min_chunk_char_length_raised(self):
        from app.core.config import settings
        assert settings.chunk_min_char_length >= 200
