"""Tests for app.rag.rag_flow — requirement decomposition and merge."""
from __future__ import annotations

from types import SimpleNamespace

from app.rag.rag_flow import (
    _classify_sub_requirement,
    decompose_requirement,
    merge_retrieval,
)


class TestClassifySubRequirement:
    def test_qualification(self):
        assert _classify_sub_requirement("投标人须具备承装修试资质") == "QUALIFICATION"

    def test_performance(self):
        assert _classify_sub_requirement("近三年类似工程业绩不少于3项") == "PERFORMANCE"

    def test_tech_param(self):
        assert _classify_sub_requirement("变压器容量不低于100MVA") == "TECH_PARAM"

    def test_personnel(self):
        assert _classify_sub_requirement("项目经理须持有一级建造师证") == "PERSONNEL"

    def test_must(self):
        assert _classify_sub_requirement("投标人必须提供有效证明") == "MUST"

    def test_general(self):
        assert _classify_sub_requirement("其他补充说明") == "GENERAL"

    def test_voltage_kv_without_qualification_keyword(self):
        assert _classify_sub_requirement("额定电压110kV变压器") == "TECH_PARAM"

    def test_voltage_level_matches_qualification_first(self):
        # "电压等级" contains "等级" which matches QUALIFICATION before TECH_PARAM
        assert _classify_sub_requirement("电压等级110kV") == "QUALIFICATION"


class TestDecomposeRequirement:
    def test_single_requirement(self):
        result = decompose_requirement("投标人须具备承装修试资质")
        assert len(result) == 1
        assert result[0].sub_id == "sub-1"
        assert result[0].category == "QUALIFICATION"

    def test_comma_separated(self):
        result = decompose_requirement("投标人须具备承装修试资质，近三年类似工程业绩不少于3项")
        assert len(result) == 2

    def test_semicolon_separated(self):
        result = decompose_requirement("投标人须具备承装修试资质；近三年类似工程业绩不少于3项；项目经理须持有一级建造师证")
        assert len(result) >= 2

    def test_short_fragments_merged(self):
        result = decompose_requirement("投标人须具备资质，且有效期内")
        # "且有效期内" is short (<8) and starts with continuation word, should merge
        assert len(result) == 1

    def test_empty_returns_general(self):
        result = decompose_requirement("")
        assert len(result) == 1
        assert result[0].category == "GENERAL"

    def test_sub_ids_sequential(self):
        result = decompose_requirement("条件一，条件二条件三，条件四条件五")
        ids = [r.sub_id for r in result]
        for i, sid in enumerate(ids, start=1):
            assert sid == f"sub-{i}"


class TestMergeRetrieval:
    def _make_hit(self, chunk_id: str) -> SimpleNamespace:
        return SimpleNamespace(chunk_id=chunk_id, text="t", score=0.9)

    def test_basic_merge(self):
        retrieval = {
            "sub-1": [self._make_hit("c1"), self._make_hit("c2")],
            "sub-2": [self._make_hit("c2"), self._make_hit("c3")],
        }
        merged_ids, coverage_map, merged_hits = merge_retrieval(retrieval)
        assert set(merged_ids) == {"c1", "c2", "c3"}
        assert "c1" in coverage_map["sub-1"]
        assert "c2" in coverage_map["sub-1"]
        assert "c2" in coverage_map["sub-2"]

    def test_dedup(self):
        retrieval = {
            "sub-1": [self._make_hit("c1")],
            "sub-2": [self._make_hit("c1")],
        }
        merged_ids, _, merged_hits = merge_retrieval(retrieval)
        assert len(merged_ids) == 1
        assert len(merged_hits) == 1

    def test_empty(self):
        merged_ids, coverage_map, merged_hits = merge_retrieval({})
        assert merged_ids == []
        assert coverage_map == {}
        assert merged_hits == []
