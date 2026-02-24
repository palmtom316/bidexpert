"""Task 8: 专家库分类扩展 — tests.

Covers:
- R01: _STRUCTURED_CATEGORY_MAP must have >= 10 categories
- R01: ExpertLibraryStructuredIngestRequest must have matching item fields
"""
from __future__ import annotations

from app.services.expert_library import _STRUCTURED_CATEGORY_MAP
from app.schemas.contracts import ExpertLibraryStructuredIngestRequest


# ---------------------------------------------------------------------------
# Category map expansion
# ---------------------------------------------------------------------------

def test_category_map_has_at_least_10_entries() -> None:
    assert len(_STRUCTURED_CATEGORY_MAP) >= 10, (
        f"Only {len(_STRUCTURED_CATEGORY_MAP)} categories, need >= 10"
    )


def test_category_map_has_original_four() -> None:
    for key in ("STANDARD", "COMPANY_PERFORMANCE", "COMPANY_QUALIFICATION", "PM_QUALIFICATION_PERFORMANCE"):
        assert key in _STRUCTURED_CATEGORY_MAP, f"Missing original category: {key}"


EXPECTED_NEW_CATEGORIES = [
    "SAFETY_PRODUCTION",
    "QUALITY_MANAGEMENT",
    "ENVIRONMENTAL_PROTECTION",
    "CONSTRUCTION_METHOD",
    "EQUIPMENT_MATERIAL",
    "FINANCIAL_CREDIT",
]


def test_category_map_has_safety_production() -> None:
    assert "SAFETY_PRODUCTION" in _STRUCTURED_CATEGORY_MAP


def test_category_map_has_quality_management() -> None:
    assert "QUALITY_MANAGEMENT" in _STRUCTURED_CATEGORY_MAP


def test_category_map_has_environmental_protection() -> None:
    assert "ENVIRONMENTAL_PROTECTION" in _STRUCTURED_CATEGORY_MAP


def test_category_map_has_construction_method() -> None:
    assert "CONSTRUCTION_METHOD" in _STRUCTURED_CATEGORY_MAP


def test_category_map_has_equipment_material() -> None:
    assert "EQUIPMENT_MATERIAL" in _STRUCTURED_CATEGORY_MAP


def test_category_map_has_financial_credit() -> None:
    assert "FINANCIAL_CREDIT" in _STRUCTURED_CATEGORY_MAP


# ---------------------------------------------------------------------------
# Each category tuple has (label, doc_type, section_type)
# ---------------------------------------------------------------------------

def test_category_map_values_are_3_tuples() -> None:
    for key, value in _STRUCTURED_CATEGORY_MAP.items():
        assert isinstance(value, tuple) and len(value) == 3, (
            f"Category {key} must be a 3-tuple, got {value!r}"
        )


# ---------------------------------------------------------------------------
# Ingest request has matching fields
# ---------------------------------------------------------------------------

def test_ingest_request_has_safety_production_items() -> None:
    req = ExpertLibraryStructuredIngestRequest(safety_production_items=["doc1"])
    assert req.safety_production_items == ["doc1"]


def test_ingest_request_has_quality_management_items() -> None:
    req = ExpertLibraryStructuredIngestRequest(quality_management_items=["doc1"])
    assert req.quality_management_items == ["doc1"]


def test_ingest_request_has_construction_method_items() -> None:
    req = ExpertLibraryStructuredIngestRequest(construction_method_items=["doc1"])
    assert req.construction_method_items == ["doc1"]
