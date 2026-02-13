from __future__ import annotations

from datetime import date, timedelta

from app.services.generation_pipeline import _expiry_warnings
from app.services.governance import remaining_budget, reserve_budget, reset_budget
from app.services.semantic_cache import build_cache_key, set_cache, get_cache


def test_cache_key_is_deterministic() -> None:
    key1 = build_cache_key(
        industry_tag="政企",
        tender_template_id="tmpl-1",
        requirement_text="必须具备一级资质",
        evidence_ids=["e2", "e1"],
    )
    key2 = build_cache_key(
        industry_tag="政企",
        tender_template_id="tmpl-1",
        requirement_text="必须具备一级资质",
        evidence_ids=["e1", "e2"],
    )
    assert key1 == key2


def test_cache_set_and_get() -> None:
    key = build_cache_key("政企", "tmpl-1", "要求A", ["e1"])
    set_cache(key, {"status": "SUPPORTED"}, ttl_seconds=60)
    assert get_cache(key) == {"status": "SUPPORTED"}


def test_budget_reserve_and_remaining() -> None:
    project_id = "p-v32"
    reset_budget(project_id)
    ok, _ = reserve_budget(project_id, 1000)
    assert ok is True
    assert remaining_budget(project_id) > 0


def test_expiry_warning_for_soon_expired_evidence() -> None:
    near_expiry = (date.today() + timedelta(days=7)).isoformat()
    warnings = _expiry_warnings([{"chunk_id": "c1", "valid_to": near_expiry}])
    assert any(w.startswith("evidence_near_expiry:c1") for w in warnings)
