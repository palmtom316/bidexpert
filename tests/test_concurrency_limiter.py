"""Tests for app.services.concurrency_limiter — local slot management."""
from __future__ import annotations


import pytest

from app.services.concurrency_limiter import (
    ConcurrencyLimitExceeded,
    DEFAULT_LIMITS,
    _local_slot,
    _normalize_task,
)


class TestNormalizeTask:
    def test_lowercase(self):
        assert _normalize_task("GENERATE") == "generate"

    def test_strips(self):
        assert _normalize_task("  review  ") == "review"

    def test_empty_defaults_to_generate(self):
        assert _normalize_task("") == "generate"

    def test_none_defaults_to_generate(self):
        assert _normalize_task(None) == "generate"


class TestDefaultLimits:
    def test_generate_limit(self):
        assert DEFAULT_LIMITS["generate"] == 3

    def test_extract_limit(self):
        assert DEFAULT_LIMITS["extract"] == 2

    def test_review_limit(self):
        assert DEFAULT_LIMITS["review"] == 2


class TestLocalSlot:
    def test_acquire_and_release(self):
        with _local_slot("test:slot1", 2):
            pass  # should not raise

    def test_exceeds_limit(self):
        # Fill up the slot
        from app.services.concurrency_limiter import _LOCAL_COUNTS, _LOCAL_LOCK
        with _LOCAL_LOCK:
            _LOCAL_COUNTS["test:exceed"] = 2
        try:
            with pytest.raises(ConcurrencyLimitExceeded):
                with _local_slot("test:exceed", 2):
                    pass
        finally:
            with _LOCAL_LOCK:
                _LOCAL_COUNTS.pop("test:exceed", None)

    def test_release_decrements(self):
        from app.services.concurrency_limiter import _LOCAL_COUNTS, _LOCAL_LOCK
        with _local_slot("test:decrement", 5):
            with _LOCAL_LOCK:
                assert _LOCAL_COUNTS.get("test:decrement", 0) == 1
        with _LOCAL_LOCK:
            assert "test:decrement" not in _LOCAL_COUNTS

    def test_concurrent_slots(self):
        """Two concurrent slots within limit should work."""
        from app.services.concurrency_limiter import _LOCAL_COUNTS, _LOCAL_LOCK
        with _local_slot("test:concurrent", 3):
            with _local_slot("test:concurrent", 3):
                with _LOCAL_LOCK:
                    assert _LOCAL_COUNTS["test:concurrent"] == 2
        with _LOCAL_LOCK:
            assert "test:concurrent" not in _LOCAL_COUNTS

    def test_release_on_exception(self):
        """Slot should be released even if body raises."""
        from app.services.concurrency_limiter import _LOCAL_COUNTS, _LOCAL_LOCK
        with pytest.raises(RuntimeError):
            with _local_slot("test:exception", 5):
                raise RuntimeError("boom")
        with _LOCAL_LOCK:
            assert "test:exception" not in _LOCAL_COUNTS
