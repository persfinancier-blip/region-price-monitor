"""PgTaskQueue tests — require a real Postgres; skip cleanly when unreachable."""

import datetime
import os
import subprocess
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import make_engine
from app.enums import Marketplace, QueueStatus, RunMode
from app.queue.base import Pair
from app.queue.postgres import PgTaskQueue
from app.repositories import ProductRepository, RegionRepository, RunRepository

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


async def _seed_run_and_pairs(session: AsyncSession, n: int) -> tuple[int, list[Pair]]:
    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)
    run_repo = RunRepository(session)

    pairs = []
    for i in range(n):
        product = await product_repo.upsert(
            marketplace=Marketplace.WB, sku=f"queue-test-sku-{i}", url="https://example.com/p", name="P"
        )
        region = await region_repo.upsert(code=f"queue-test-region-{i}", name="R", geo={})
        pairs.append(Pair(product_id=product.id, region_id=region.id))
    run = await run_repo.create(mode=RunMode.MANUAL)
    await session.commit()
    return run.id, pairs


async def test_enqueue_creates_pending_rows(session: AsyncSession) -> None:
    run_id, pairs = await _seed_run_and_pairs(session, 3)
    queue = PgTaskQueue(session)

    await queue.enqueue(run_id, pairs)
    await session.commit()

    claimed = await queue.claim(10)
    await session.commit()

    claimed_for_run = [item for item in claimed if item.run_id == run_id]
    assert len(claimed_for_run) == 3


async def test_concurrent_claim_returns_disjoint_items(session: AsyncSession) -> None:
    run_id, pairs = await _seed_run_and_pairs(session, 4)
    queue = PgTaskQueue(session)
    await queue.enqueue(run_id, pairs)
    await session.commit()

    engine = make_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with factory() as session_a, factory() as session_b:
        queue_a = PgTaskQueue(session_a)
        queue_b = PgTaskQueue(session_b)

        claimed_a = await queue_a.claim(2)
        claimed_b = await queue_b.claim(2)

        await session_a.commit()
        await session_b.commit()

        ids_a = {item.id for item in claimed_a if item.run_id == run_id}
        ids_b = {item.id for item in claimed_b if item.run_id == run_id}

        assert ids_a
        assert ids_b
        assert ids_a.isdisjoint(ids_b)

    await engine.dispose()


async def test_claim_sets_status_and_locked_at(session: AsyncSession) -> None:
    run_id, pairs = await _seed_run_and_pairs(session, 1)
    queue = PgTaskQueue(session)
    await queue.enqueue(run_id, pairs)
    await session.commit()

    claimed = await queue.claim(10)
    await session.commit()

    item = next(i for i in claimed if i.run_id == run_id)
    assert item is not None

    from app.repositories import MeasureQueueRepository

    queue_repo = MeasureQueueRepository(session)
    row = await queue_repo.get(item.id)
    assert row is not None
    assert row.status == QueueStatus.IN_PROGRESS
    assert row.locked_at is not None


async def test_complete_sets_terminal_status(session: AsyncSession) -> None:
    run_id, pairs = await _seed_run_and_pairs(session, 1)
    queue = PgTaskQueue(session)
    await queue.enqueue(run_id, pairs)
    await session.commit()

    claimed = await queue.claim(10)
    await session.commit()
    item = next(i for i in claimed if i.run_id == run_id)

    await queue.complete(item, QueueStatus.DONE)
    await session.commit()

    from app.repositories import MeasureQueueRepository

    queue_repo = MeasureQueueRepository(session)
    row = await queue_repo.get(item.id)
    assert row is not None
    assert row.status == QueueStatus.DONE


async def test_reclaim_stale_returns_item_to_pending(session: AsyncSession) -> None:
    run_id, pairs = await _seed_run_and_pairs(session, 1)
    queue = PgTaskQueue(session)
    await queue.enqueue(run_id, pairs)
    await session.commit()

    claimed = await queue.claim(10)
    await session.commit()
    item = next(i for i in claimed if i.run_id == run_id)

    from app.repositories import MeasureQueueRepository

    queue_repo = MeasureQueueRepository(session)
    row = await queue_repo.get(item.id)
    assert row is not None
    row.locked_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1000)
    await session.flush()
    await session.commit()

    reclaimed = await queue.reclaim_stale(datetime.timedelta(seconds=600))
    await session.commit()

    assert reclaimed >= 1
    row = await queue_repo.get(item.id)
    assert row is not None
    assert row.status == QueueStatus.PENDING
