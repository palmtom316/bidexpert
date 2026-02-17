from __future__ import annotations

import json
import logging

from app.core.logging import JsonLogFormatter, _build_formatter, _resolve_log_level


def test_resolve_log_level_defaults_to_info() -> None:
    assert _resolve_log_level("warning") == logging.WARNING
    assert _resolve_log_level("unknown-level") == logging.INFO


def test_build_formatter_json_mode() -> None:
    formatter = _build_formatter("json")
    assert isinstance(formatter, JsonLogFormatter)


def test_json_log_formatter_payload() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello %s",
        args=("bidexpert",),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello bidexpert"
    assert "timestamp" in payload

