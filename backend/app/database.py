from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _build_engine():
    """Build an async engine appropriate for the configured backend.

    SQLite's aiosqlite driver doesn't accept pool_size/max_overflow; pass
    connect_args to enable shared-cache access and foreign keys instead.
    """
    if settings.is_sqlite:
        return create_async_engine(
            settings.database_url,
            echo=settings.debug,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.debug,
        pool_pre_ping=True,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def enable_sqlite_fks() -> None:
    """Enable foreign_keys PRAGMA for every new SQLite connection."""
    if not settings.is_sqlite:
        return
    from sqlalchemy import event

    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
