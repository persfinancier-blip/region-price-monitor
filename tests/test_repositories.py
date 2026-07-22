"""Repository tests — require a real Postgres; skip cleanly when unreachable."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import make_engine
from app.enums import Marketplace
from app.repositories import ProductRepository, RegionRepository

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

if not TEST_DATABASE_URL:
    pytest.skip("no TEST_DATABASE_URL/DATABASE_URL configured", allow_module_level=True)

try:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        capture_output=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
    )
except (subprocess.CalledProcessError, FileNotFoundError) as exc:
    pytest.skip(f"database unreachable: {exc}", allow_module_level=True)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"database unreachable: {exc}")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()
    await engine.dispose()


async def test_product_upsert_is_idempotent(session: AsyncSession) -> None:
    repo = ProductRepository(session)
    first = await repo.upsert(
        marketplace=Marketplace.WB, sku="test-sku-1", url="https://example.com/1", name="A"
    )
    second = await repo.upsert(
        marketplace=Marketplace.WB, sku="test-sku-1", url="https://example.com/1", name="B"
    )
    await session.flush()

    assert first.id == second.id
    assert second.name == "B"


async def test_product_list_active(session: AsyncSession) -> None:
    repo = ProductRepository(session)
    await repo.upsert(
        marketplace=Marketplace.WB, sku="test-sku-active", url="https://example.com/a", name="Active"
    )
    await repo.upsert(
        marketplace=Marketplace.WB,
        sku="test-sku-inactive",
        url="https://example.com/b",
        name="Inactive",
        is_active=False,
    )
    await session.flush()

    active = await repo.list_active()
    skus = {p.sku for p in active}
    assert "test-sku-active" in skus
    assert "test-sku-inactive" not in skus


async def test_region_upsert_is_idempotent(session: AsyncSession) -> None:
    repo = RegionRepository(session)
    first = await repo.upsert(code="test-region", name="Test Region", geo={"wb": {"dest": 1}})
    second = await repo.upsert(code="test-region", name="Test Region 2", geo={"wb": {"dest": 2}})
    await session.flush()

    assert first.id == second.id
    assert second.name == "Test Region 2"


async def test_region_list_active(session: AsyncSession) -> None:
    repo = RegionRepository(session)
    await repo.upsert(code="test-region-active", name="Active", geo={})
    await repo.upsert(code="test-region-inactive", name="Inactive", geo={}, is_active=False)
    await session.flush()

    active = await repo.list_active()
    codes = {r.code for r in active}
    assert "test-region-active" in codes
    assert "test-region-inactive" not in codes
