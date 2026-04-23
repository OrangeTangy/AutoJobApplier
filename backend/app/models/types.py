from __future__ import annotations

import uuid

from sqlalchemy import CHAR, String
from sqlalchemy.dialects.postgresql import INET as PG_INET
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import JSON as SA_JSON
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent GUID — UUID on Postgres, CHAR(36) on SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class JSON(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite."""

    impl = SA_JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(SA_JSON())


class INET(TypeDecorator):
    """INET on Postgres, plain TEXT on SQLite."""

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_INET())
        return dialect.type_descriptor(String(45))


JSONB = JSON


def UUID(as_uuid: bool = True) -> GUID:  # noqa: N802 — drop-in for postgresql.UUID
    """Factory to preserve `UUID(as_uuid=True)` call sites."""
    return GUID()

