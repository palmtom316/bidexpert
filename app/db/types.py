from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, CHAR, Text
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Cross-dialect UUID type.

    Uses PostgreSQL UUID in Postgres and CHAR(36) elsewhere.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return parsed
        return str(parsed)

    def process_result_value(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class StringListType(TypeDecorator[list[str]]):
    """Cross-dialect string-list type.

    Uses PostgreSQL ARRAY(TEXT) in Postgres and JSON array elsewhere.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGARRAY(Text()))
        return dialect.type_descriptor(JSON)

    def process_bind_param(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return []
        if not isinstance(value, list):
            value = list(value)
        return [str(item) for item in value]

    def process_result_value(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


class UUIDListType(TypeDecorator[list[uuid.UUID]]):
    """Cross-dialect UUID-list type.

    Uses PostgreSQL ARRAY(UUID) in Postgres and JSON array elsewhere.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGARRAY(PGUUID(as_uuid=True)))
        return dialect.type_descriptor(JSON)

    def process_bind_param(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return []
        if not isinstance(value, list):
            value = list(value)
        parsed = [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]
        if dialect.name == "postgresql":
            return parsed
        return [str(item) for item in parsed]

    def process_result_value(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]
