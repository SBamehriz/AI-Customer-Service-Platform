"""Database engine, session factory and declarative base."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from .config import DATA_DIR, settings

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Naive UTC timestamp."""
    return datetime.now(UTC).replace(tzinfo=None)


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in settings.DATABASE_URL:
            kwargs["poolclass"] = StaticPool
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        return kwargs
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, **_engine_kwargs())

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session that commits on success."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create any missing tables, and add any missing nullable columns."""
    from . import models  # noqa: F401, the import is what registers the mappings

    async with engine.begin() as conn:
        if settings.is_sqlite:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(connection) -> None:
    """Add columns the models declare and the database does not have yet."""
    from sqlalchemy import inspect, text

    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable or column.primary_key:
                logger.warning(
                    "Column %s.%s is missing and cannot be added automatically",
                    table.name,
                    column.name,
                )
                continue
            type_sql = column.type.compile(connection.dialect)
            connection.execute(
                text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {type_sql}')
            )
            logger.info("Added missing column %s.%s", table.name, column.name)


async def close_db() -> None:
    await engine.dispose()
