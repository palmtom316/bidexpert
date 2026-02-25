"""Tests for expert library classification system expansion.

TDD RED phase: verifies all 10 categories are available for structured ingest
and that doc_type filtering is wired into Qdrant queries.
"""
from __future__ import annotations

import pytest

from app.services.expert_library import _STRUCTURED_CATEGORY_MAP


class TestCategoryMapComplete:
    """All 10 categories should be in the structured category map."""

    EXPECTED_CATEGORIES = [
        "STANDARD",
        "COMPANY_PERFORMANCE",
        "COMPANY_QUALIFICATION",
        "PM_QUALIFICATION_PERFORMANCE",
        "SAFETY_PRODUCTION",
        "QUALITY_MANAGEMENT",
        "ENVIRONMENTAL_PROTECTION",
        "CONSTRUCTION_METHOD",
        "EQUIPMENT_MATERIAL",
        "FINANCIAL_CREDIT",
    ]

    @pytest.mark.parametrize("category", EXPECTED_CATEGORIES)
    def test_category_exists(self, category):
        assert category in _STRUCTURED_CATEGORY_MAP

    def test_category_tuple_structure(self):
        for key, value in _STRUCTURED_CATEGORY_MAP.items():
            assert len(value) == 3, f"{key} should have (title, doc_type, section_type)"
            title, doc_type, section_type = value
            assert isinstance(title, str) and title
            assert isinstance(doc_type, str) and doc_type
            assert isinstance(section_type, str) and section_type


class TestStructuredIngestAcceptsAllCategories:
    """ingest_structured_expert_knowledge should accept all 10 categories."""

    def test_function_signature_has_all_category_params(self):
        """The function should accept keyword args for all categories."""
        import inspect
        from app.services.expert_library import ingest_structured_expert_knowledge
        sig = inspect.signature(ingest_structured_expert_knowledge)
        param_names = set(sig.parameters.keys())
        # All 10 categories should have corresponding _items parameters
        assert "safety_production_items" in param_names
        assert "quality_management_items" in param_names
        assert "environmental_protection_items" in param_names
        assert "construction_method_items" in param_names
        assert "equipment_material_items" in param_names
        assert "financial_credit_items" in param_names


class TestQdrantDocTypeFilter:
    """Qdrant query filter should support doc_type filtering."""

    def test_build_query_filter_accepts_doc_type(self):
        """_build_query_filter should accept a doc_type parameter."""
        import inspect
        from app.services.qdrant_store import QdrantStore
        sig = inspect.signature(QdrantStore._build_query_filter)
        assert "doc_type" in sig.parameters

    def test_search_accepts_doc_type(self):
        """search() should accept a doc_type parameter."""
        import inspect
        from app.services.qdrant_store import QdrantStore
        sig = inspect.signature(QdrantStore.search)
        assert "doc_type" in sig.parameters
