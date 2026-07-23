"""Pure RunMetrics arithmetic; DB-gated aggregation test skips cleanly without Postgres."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import make_engine
from app.enums import Outcome
from app.obs.metrics import compute_run_metrics, metrics_from_counts, to_prometheus


def test_metrics_from_counts_all_ok() -> None:
    metrics = metrics_from_counts(1, {Outcome.OK.value: 10}, 5000)

    assert metrics.total == 10
    assert metrics.success_rate == 1.0
    assert metrics.ban_rate == 0.0
    assert metrics.error_rate == 0.0
    assert metrics.avg_duration_ms == 500.0
    assert metrics.attempts_per_success == 1.0


def test_metrics_from_counts_mixed() -> None:
    counts = {
        Outcome.OK.value: 6,
        Outcome.HARD_BAN.value: 2,
        Outcome.SOFT_BAN.value: 1,
        Outcome.TIMEOUT.value: 1,
    }
    metrics = metrics_from_counts(2, counts, 10000)

    assert metrics.total == 10
    assert metrics.success_rate == 0.6
    assert metrics.ban_rate == 0.3
    assert metrics.error_rate == 0.1
    assert metrics.avg_duration_ms == 1000.0
    assert metrics.attempts_per_success == 10 / 6


def test_metrics_from_counts_no_success_uses_total_as_worst_case() -> None:
    metrics = metrics_from_counts(3, {Outcome.HARD_BAN.value: 4}, 1000)

    assert metrics.success_rate == 0.0
    assert metrics.attempts_per_success == 4.0


def test_metrics_from_counts_empty_guards_divide_by_zero() -> None:
    metrics = metrics_from_counts(4, {}, 0)

    assert metrics.total == 0
    assert metrics.success_rate == 0.0
    assert metrics.ban_rate == 0.0
    assert metrics.error_rate == 0.0
    assert metrics.avg_duration_ms == 0.0
    assert metrics.attempts_per_success == 0.0


def test_to_prometheus_well_formed() -> None:
    metrics = metrics_from_counts(7, {Outcome.OK.value: 9, Outcome.HARD_BAN.value: 1}, 2000)

    text = to_prometheus(metrics)

    assert 'rpm_run_success_rate{run_id="7"} 0.9' in text
    assert 'rpm_run_outcome_total{run_id="7",outcome="hard_ban"} 1' in text
    assert 'rpm_run_outcome_total{run_id="7",outcome="ok"} 9' in text
    for line in text.strip().splitlines():
        assert line.startswith("rpm_run_")


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


async def test_compute_run_metrics_aggregates_mixed_attempts(session: AsyncSession) -> None:
    from app.enums import Marketplace, RunMode
    from app.repositories import (
        AttemptRepository,
        MeasureQueueRepository,
        ProductRepository,
        RegionRepository,
        RunRepository,
    )

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)
    run_repo = RunRepository(session)
    queue_repo = MeasureQueueRepository(session)
    attempt_repo = AttemptRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="metrics-test-sku", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="metrics-test-region", name="R", geo={"wb": {"dest": 1}})
    run = await run_repo.create(mode=RunMode.MANUAL)
    await session.flush()

    queue_item = await queue_repo.create(run_id=run.id, product_id=product.id, region_id=region.id)
    await attempt_repo.add(
        queue_id=queue_item.id, proxy_ref="static:x:host", outcome=Outcome.OK, duration_ms=100
    )

    queue_item2 = await queue_repo.create(run_id=run.id, product_id=product.id, region_id=region.id)
    await attempt_repo.add(
        queue_id=queue_item2.id, proxy_ref="static:x:host", outcome=Outcome.HARD_BAN, duration_ms=200
    )
    await session.flush()

    metrics = await compute_run_metrics(session, run.id)

    assert metrics.total == 2
    assert metrics.by_outcome[Outcome.OK.value] == 1
    assert metrics.by_outcome[Outcome.HARD_BAN.value] == 1
    assert metrics.success_rate == 0.5
    assert metrics.ban_rate == 0.5
    assert metrics.avg_duration_ms == 150.0
