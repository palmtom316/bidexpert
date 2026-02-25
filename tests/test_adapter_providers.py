"""Tests for app.services.adapters.providers — MockAdapter and VoyageAdapter."""
from __future__ import annotations

import pytest

from app.services.adapters.base import (
    AdapterUnavailableError,
    ComplianceReviewRequest,
    GenerationRequest,
    QueryRewriteRequest,
    ReviewRequest,
)
from app.services.adapters.providers import MockAdapter, VoyageAdapter


def _gen_request(**overrides) -> GenerationRequest:
    defaults = dict(
        requirement_text="投标人须具备承装修试资质",
        evidence_texts=["我公司具备承装修试三级资质"],
        evidence_ids=["e-1"],
        model="mock-model",
        api_key=None,
        base_url=None,
        global_facts={},
        relevant_requirements=["投标人须具备承装修试资质"],
        relevant_scoring=[],
        top_chunks=[],
    )
    defaults.update(overrides)
    return GenerationRequest(**defaults)


def _review_request(**overrides) -> ReviewRequest:
    defaults = dict(
        draft_text="这是一段足够长的投标文本内容用于测试审查功能的正确性验证",
        evidence_texts=["证据文本"],
        model="mock-model",
        api_key=None,
        base_url=None,
    )
    defaults.update(overrides)
    return ReviewRequest(**defaults)


class TestMockAdapterGenerate:
    def test_returns_result(self):
        adapter = MockAdapter()
        result = adapter.generate(_gen_request())
        assert result.provider == "mock"
        assert result.text
        assert result.content_json is not None

    def test_empty_evidence(self):
        adapter = MockAdapter()
        result = adapter.generate(_gen_request(evidence_texts=[], evidence_ids=[]))
        assert "NEED_HUMAN_INPUT" in result.text


class TestMockAdapterReview:
    def test_approved_long_draft(self):
        adapter = MockAdapter()
        result = adapter.review(_review_request())
        assert result.approved is True
        assert result.issues == []

    def test_rejected_empty_draft(self):
        adapter = MockAdapter()
        result = adapter.review(_review_request(draft_text=""))
        assert result.approved is False
        assert "empty_draft" in result.issues

    def test_rejected_short_draft(self):
        adapter = MockAdapter()
        result = adapter.review(_review_request(draft_text="短"))
        assert result.approved is False
        assert "draft_too_short" in result.issues


class TestMockAdapterComplianceReview:
    def test_pass(self):
        adapter = MockAdapter()
        req = ComplianceReviewRequest(
            content_text="正常内容",
            requirements=[],
            model="mock",
            api_key=None,
            base_url=None,
        )
        result = adapter.compliance_review(req)
        assert result.status == "PASS"

    def test_fail_keyword(self):
        adapter = MockAdapter()
        req = ComplianceReviewRequest(
            content_text="this will fail",
            requirements=[],
            model="mock",
            api_key=None,
            base_url=None,
        )
        result = adapter.compliance_review(req)
        assert result.status == "FAIL"


class TestMockAdapterRewriteQuery:
    def test_collapses_whitespace(self):
        adapter = MockAdapter()
        req = QueryRewriteRequest(query="hello   world", model="mock", api_key=None, base_url=None)
        result = adapter.rewrite_query(req)
        assert result.rewritten_query == "hello world"


class TestVoyageAdapter:
    def test_generate_raises(self):
        adapter = VoyageAdapter()
        with pytest.raises(AdapterUnavailableError, match="embedding"):
            adapter.generate(_gen_request())

    def test_review_raises(self):
        adapter = VoyageAdapter()
        with pytest.raises(AdapterUnavailableError, match="embedding"):
            adapter.review(_review_request())

    def test_rewrite_raises(self):
        adapter = VoyageAdapter()
        req = QueryRewriteRequest(query="test", model="v", api_key=None, base_url=None)
        with pytest.raises(AdapterUnavailableError, match="embedding"):
            adapter.rewrite_query(req)
