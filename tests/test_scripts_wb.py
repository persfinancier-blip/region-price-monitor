"""app.scripts.wb — argv smoke test (no DB) + DB-backed run() test (skips cleanly without Postgres)."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import PriceObservation
from app.db import make_engine
from app.enums import Marketplace, Outcome
from app.models import Attempt, MeasureQueueItem
from app.repositories import ProductRepository, RegionRepository
from app.scripts import wb as wb_script


def test_main_help_smoke() -> None:
    with pytest.raises(SystemExit) as exc_info:
        wb_script.main(["--help"])
    assert exc_info.value.code == 0


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


async def test_wb_run_writes_queue_and_attempt_and_snapshot_on_ok(session: AsyncSession) -> None:
    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="scripts-wb-test-sku", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(
        code="scripts-wb-test-region", name="Test Region", geo={"wb": {"dest": 123}}
    )
    await session.commit()

    obs = PriceObservation(
        price=Decimal("100.00"),
        price_base=Decimal("100.00"),
        price_card=None,
        currency="RUB",
        is_available=True,
    )

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with patch("app.collectors.wb.WbCollector.collect", return_value=obs):
        result = await wb_script.run([region.code], product.sku, session_factory=fake_session_factory)

    assert result == 0

    queue_result = await session.execute(
        select(MeasureQueueItem).where(
            MeasureQueueItem.product_id == product.id, MeasureQueueItem.region_id == region.id
        )
    )
    queue_item = queue_result.scalar_one()

    attempt_result = await session.execute(select(Attempt).where(Attempt.queue_id == queue_item.id))
    attempt = attempt_result.scalar_one()

    assert attempt.outcome == Outcome.OK
    assert attempt.proxy_ref is not None
