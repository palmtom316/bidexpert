from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.endpoints import stats


class _ExecResult:
    def __init__(self, *, scalar=None, one=None, all_rows=None, iter_rows=None):  # noqa: ANN001
        self._scalar = scalar
        self._one = one
        self._all_rows = all_rows or []
        self._iter_rows = iter_rows or []

    def scalar(self):  # noqa: ANN201
        return self._scalar

    def one(self):  # noqa: ANN201
        return self._one

    def all(self):  # noqa: ANN201
        return self._all_rows

    def __iter__(self):  # noqa: ANN204
        return iter(self._iter_rows)


class _DbStub:
    def __init__(self, results: list[_ExecResult]) -> None:
        self._results = list(results)
        self.added: list[object] = []

    def execute(self, _stmt):  # noqa: ANN001, ANN201
        if not self._results:
            raise AssertionError("unexpected execute call")
        return self._results.pop(0)

    def add(self, item):  # noqa: ANN001, ANN201
        self.added.append(item)

    def commit(self):  # noqa: ANN201
        return None


def test_get_expert_quality_stats_rejects_invalid_project_id() -> None:
    with pytest.raises(HTTPException, match="invalid project_id"):
        stats.get_expert_quality_stats(project_id="bad-id", db=SimpleNamespace(execute=lambda _stmt: None))


def test_get_expert_model_compare_rejects_invalid_project_id() -> None:
    with pytest.raises(HTTPException, match="invalid project_id"):
        stats.get_expert_model_compare(project_id="bad-id", db=SimpleNamespace(execute=lambda _stmt: None))


def test_get_expert_quality_stats_computes_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "get_expert_library_thresholds",
        lambda: {
            "values": {"low_confidence": 0.6, "strong_review_confidence": 0.75},
            "source": {"runtime_path": "/tmp/thresholds.runtime.yaml"},
        },
    )
    db = _DbStub(
        [
            _ExecResult(scalar=3),  # doc_count
            _ExecResult(one=(10, 82.5)),  # chunk_count + avg
            _ExecResult(scalar=2),  # low_quality_count
            _ExecResult(iter_rows=[(["PRICING_RELATED"],), ([],), (["X"],)]),  # pricing tags
            _ExecResult(all_rows=[(stats.KBIngestStep.KB_READY, 5), (stats.KBIngestStep.FAILED, 1)]),
            _ExecResult(
                iter_rows=[
                    (
                        {
                            "quality_signals": {
                                "schema_passed": True,
                                "key_field_completeness": 0.8,
                                "fallback_triggered": False,
                                "manual_review_required": True,
                                "evidence_coverage": 0.9,
                            }
                        },
                    ),
                    (
                        {
                            "quality_signals": {
                                "schema_passed": False,
                                "key_field_completeness": 0.6,
                                "fallback_triggered": True,
                                "manual_review_required": False,
                                "evidence_coverage": 0.5,
                            }
                        },
                    ),
                ]
            ),
        ]
    )

    resp = stats.get_expert_quality_stats(project_id=None, industry_tag=None, db=db)

    assert resp.stats.doc_count == 3
    assert resp.stats.chunk_count == 10
    assert resp.stats.avg_quality_score == 82.5
    assert resp.stats.low_quality_chunk_count == 2
    assert resp.stats.pricing_related_chunk_count == 1
    assert resp.stats.kb_ready_count == 5
    assert resp.stats.kb_failed_count == 1
    assert resp.stats.low_quality_threshold == 60.0
    assert resp.stats.schema_pass_rate == 0.5
    assert resp.stats.key_field_completeness_rate == 0.7
    assert resp.stats.fallback_trigger_rate == 0.5
    assert resp.stats.manual_review_rate == 0.5
    assert resp.stats.evidence_coverage_rate == 0.7


def test_get_expert_model_compare_maps_rows() -> None:
    db = _DbStub(
        [
            _ExecResult(all_rows=[]),  # failure rows
            _ExecResult(
                all_rows=[
                    ("qwen-max", "GENERATE", 20, 18, 2, 4, 900.0, 1200.0, 400.0, 24000.0, 8000.0),
                ]
            )
        ]
    )

    resp = stats.get_expert_model_compare(project_id=None, days=30, limit=20, db=db)

    assert resp.days == 30
    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.model_name == "qwen-max"
    assert item.purpose == "GENERATE"
    assert item.call_count == 20
    assert item.success_rate == 0.9
    assert item.fallback_rate == 0.1
    assert item.cache_hit_rate == 0.2
    assert item.failure_count == 2


def test_expert_thresholds_put_wraps_validation_error(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "update_expert_library_thresholds",
        lambda _payload: (_ for _ in ()).throw(ValueError("bad threshold")),
    )
    with pytest.raises(HTTPException, match="bad threshold"):
        stats.put_expert_thresholds_stats(stats.ExpertThresholdUpdateRequest(low_confidence=2.0))


def test_get_expert_threshold_recommendation_uses_quality_signal(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "get_expert_quality_stats",
        lambda **_kwargs: stats.ExpertQualityStatsResponse(
            project_id=None,
            industry_tag=None,
            stats=stats.ExpertQualityStats(
                doc_count=3,
                chunk_count=10,
                avg_quality_score=75.0,
                low_quality_chunk_count=3,
                low_quality_rate=0.3,
                pricing_related_chunk_count=0,
                kb_ready_count=2,
                kb_failed_count=1,
                low_quality_threshold=60.0,
            ),
            thresholds={
                "low_confidence": 0.6,
                "strong_review_confidence": 0.75,
                "max_section_pages": 20.0,
                "max_chunk_tokens": 1200.0,
                "chunk_overlap_tokens": 100.0,
            },
            threshold_source={},
        ),
    )
    monkeypatch.setattr(
        stats,
        "get_expert_library_go_live_thresholds",
        lambda: {
            "values": {"low_confidence": 0.64, "strong_review_confidence": 0.79},
            "source": {},
        },
    )

    resp = stats.get_expert_threshold_recommendation(project_id=None, industry_tag=None, db=SimpleNamespace())
    items = {item.key: item for item in resp.suggestions}

    assert resp.low_quality_rate == 0.3
    assert resp.kb_failed_count == 1
    assert items["low_confidence"].suggested_value > items["low_confidence"].current_value
    assert items["strong_review_confidence"].suggested_value > items["strong_review_confidence"].current_value
    assert items["low_confidence"].go_live_value == 0.64
    assert items["strong_review_confidence"].go_live_value == 0.79


def test_expert_go_live_thresholds_put_wraps_validation_error(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "update_expert_library_go_live_thresholds",
        lambda _payload: (_ for _ in ()).throw(ValueError("bad go live threshold")),
    )
    with pytest.raises(HTTPException, match="bad go live threshold"):
        stats.put_expert_go_live_thresholds_stats(stats.ExpertThresholdUpdateRequest(low_confidence=2.0))


def test_expert_go_live_threshold_publish_wraps_error(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "publish_expert_library_go_live_thresholds",
        lambda: (_ for _ in ()).throw(ValueError("go_live thresholds not found")),
    )
    with pytest.raises(HTTPException, match="go_live thresholds not found"):
        stats.post_expert_go_live_thresholds_publish(db=SimpleNamespace(add=lambda _row: None, commit=lambda: None))


def test_get_expert_quality_detail_maps_breakdown(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "get_expert_library_thresholds",
        lambda: {"values": {"low_confidence": 0.6}, "source": {}},
    )
    db = _DbStub(
        [
            _ExecResult(  # by_doc_type
                all_rows=[
                    ("STANDARD_SPEC", 2, 8, 84.0, 1),
                    ("COMPANY_QUALIFICATION", 1, 2, 90.0, 0),
                ]
            ),
            _ExecResult(  # by_ingest_step
                all_rows=[
                    (stats.KBIngestStep.KB_READY, 5),
                    (stats.KBIngestStep.FAILED, 1),
                ]
            ),
            _ExecResult(all_rows=[]),  # by_model failure rows
            _ExecResult(  # by_model
                all_rows=[
                    ("qwen-max", "GENERATE", 20, 18, 2, 4, 900.0, 1200.0, 400.0, 24000.0, 8000.0),
                ]
            ),
        ]
    )

    resp = stats.get_expert_quality_detail(project_id=None, industry_tag=None, days=30, db=db)

    assert resp.days == 30
    assert len(resp.by_doc_type) == 2
    assert resp.by_doc_type[0].doc_type == "STANDARD_SPEC"
    assert resp.by_doc_type[0].low_quality_rate == 0.125
    assert len(resp.by_ingest_step) == 2
    assert resp.by_ingest_step[0].step == "KB_READY"
    assert resp.by_ingest_step[0].ratio == round(5 / 6, 4)
    assert len(resp.by_model) == 1
    assert resp.by_model[0].model_name == "qwen-max"


def test_export_expert_quality_csv_contains_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "get_expert_quality_stats",
        lambda **_kwargs: stats.ExpertQualityStatsResponse(
            project_id=None,
            industry_tag=None,
            stats=stats.ExpertQualityStats(
                doc_count=3,
                chunk_count=10,
                avg_quality_score=82.5,
                low_quality_chunk_count=2,
                low_quality_rate=0.2,
                pricing_related_chunk_count=1,
                kb_ready_count=5,
                kb_failed_count=1,
                low_quality_threshold=60.0,
                schema_pass_rate=0.8,
                key_field_completeness_rate=0.75,
                fallback_trigger_rate=0.1,
                manual_review_rate=0.2,
                evidence_coverage_rate=0.9,
            ),
            thresholds={},
            threshold_source={},
        ),
    )
    monkeypatch.setattr(
        stats,
        "get_expert_quality_detail",
        lambda **_kwargs: stats.ExpertQualityDetailResponse(
            project_id=None,
            industry_tag=None,
            days=30,
            by_doc_type=[
                stats.ExpertDocTypeBreakdownItem(
                    doc_type="STANDARD_SPEC",
                    doc_count=2,
                    chunk_count=8,
                    avg_quality_score=84.0,
                    low_quality_chunk_count=1,
                    low_quality_rate=0.125,
                )
            ],
            by_ingest_step=[stats.ExpertIngestStepBreakdownItem(step="KB_READY", run_count=5, ratio=0.8333)],
            by_model=[
                stats.ExpertModelCompareItem(
                    model_name="qwen-max",
                    purpose="GENERATE",
                    call_count=20,
                    success_rate=0.9,
                    fallback_rate=0.1,
                    cache_hit_rate=0.2,
                    avg_latency_ms=900.0,
                    avg_input_tokens=1200.0,
                    avg_output_tokens=400.0,
                    avg_total_tokens=1600.0,
                    estimated_cost_usd=0.1234,
                    failure_count=2,
                    top_failure_type="RATE_LIMIT",
                )
            ],
        ),
    )

    resp = stats.export_expert_quality_csv(project_id=None, industry_tag=None, days=30, db=SimpleNamespace())

    assert resp.media_type.startswith("text/csv")
    assert "attachment; filename=" in resp.headers.get("Content-Disposition", "")
    content = resp.body.decode("utf-8")
    assert "dimension,name,metric,value" in content
    assert "quality_control,global,schema_pass_rate,0.8" in content
    assert "doc_type,STANDARD_SPEC,doc_count,2" in content
    assert "ingest_step,KB_READY,run_count,5" in content
    assert "model,qwen-max|GENERATE,call_count,20" in content
    assert "model,qwen-max|GENERATE,top_failure_type,RATE_LIMIT" in content


def test_get_expert_model_compare_window_merges_current_and_baseline(monkeypatch) -> None:
    monkeypatch.setattr(
        stats,
        "_query_model_compare",
        lambda **kwargs: [
            stats.ExpertModelCompareItem(
                model_name="qwen-max",
                purpose="GENERATE",
                call_count=10 if kwargs["days"] == 30 else 20,
                success_rate=0.9 if kwargs["days"] == 30 else 0.8,
                fallback_rate=0.1,
                cache_hit_rate=0.2,
                avg_latency_ms=800.0 if kwargs["days"] == 30 else 950.0,
                avg_input_tokens=1000.0,
                avg_output_tokens=300.0,
                avg_total_tokens=1300.0,
                estimated_cost_usd=0.5 if kwargs["days"] == 30 else 0.9,
                failure_count=1 if kwargs["days"] == 30 else 4,
                top_failure_type="RATE_LIMIT" if kwargs["days"] == 30 else "TIMEOUT",
            )
        ],
    )
    resp = stats.get_expert_model_compare_window(
        project_id=None,
        days=30,
        baseline_days=90,
        limit=20,
        db=SimpleNamespace(),
    )
    assert resp.days == 30
    assert resp.baseline_days == 90
    assert len(resp.items) == 1
    assert resp.items[0].delta_success_rate == 0.1


def test_expert_go_live_threshold_publish_writes_audit(monkeypatch) -> None:
    monkeypatch.setattr(stats, "get_expert_library_thresholds", lambda: {"values": {"low_confidence": 0.6}})
    monkeypatch.setattr(stats, "get_expert_library_go_live_thresholds", lambda: {"values": {"low_confidence": 0.7}})
    monkeypatch.setattr(
        stats,
        "publish_expert_library_go_live_thresholds",
        lambda: {"values": {"low_confidence": 0.7}, "source": {"runtime_path": "/tmp/a.yaml"}},
    )
    db = _DbStub([])
    resp = stats.post_expert_go_live_thresholds_publish(
        payload=stats.ExpertThresholdPublishRequest(actor_user_id="u1", reason="approve"),
        project_id=None,
        db=db,
    )
    assert resp.values["low_confidence"] == 0.7
    assert len(db.added) == 1
