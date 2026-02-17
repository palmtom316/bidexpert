from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.core.config import settings


class JsonLogFormatter(logging.Formatter):
    """Emit compact JSON logs for ingestion by log backends."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _resolve_log_level(raw_level: str) -> int:
    value = (raw_level or "INFO").strip().upper()
    return getattr(logging, value, logging.INFO)


def _build_formatter(raw_format: str) -> logging.Formatter:
    if (raw_format or "").strip().lower() == "json":
        return JsonLogFormatter()
    return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def configure_logging() -> None:
    level = _resolve_log_level(settings.log_level)
    formatter = _build_formatter(settings.log_format)
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        return

    for handler in root.handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)

