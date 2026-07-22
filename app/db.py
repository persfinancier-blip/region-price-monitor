"""Async database engine, session factory, and healthcheck."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given (or configured) DATABASE_URL."""
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True)


_engine = make_engine()
_session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the module-level engine."""
    async with _session_factory() as session:
        yield session


async def healthcheck(engine: AsyncEngine | None = None) -> bool:
    """Run SELECT 1 against the database; return True if it succeeds."""
    target = engine or _engine
    async with target.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return bool(result.scalar_one() == 1)
