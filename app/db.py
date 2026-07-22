"""Async SQLAlchemy engine/session setup and DB healthcheck."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for ORM models (populated in later phases)."""


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def healthcheck() -> bool:
    """Run SELECT 1 against the configured database."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return bool(result.scalar_one() == 1)
