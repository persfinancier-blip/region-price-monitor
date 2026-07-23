"""run_once over stubbed collectors — requires a real Postgres; skips cleanly when unreachable."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import PriceObservation
from app.config import Settings
from app.db import make_engine
from app.enums import Marketplace, Outcome, RunMode
from app.models import Attempt, MeasureQueueItem, PriceSnapshot
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


def _session_factory():
    engine = make_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    return factory


async def test_run_once_writes_snapshot_and_attempt_on_ok(session: AsyncSession) -> None:
    from app.scheduler.runner import run_once

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="runner-test-sku-ok", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="runner-test-region-ok", name="R", geo={"wb": {"dest": 1}})
    await session.commit()

    obs = PriceObservation(
        price=Decimal("100.00"),
        price_base=Decimal("100.00"),
        price_card=None,
        currency="RUB",
        is_available=True,
    )

    settings = Settings(max_concurrency=1, retry_limit=1, queue_claim_batch=10)
    factory = _session_factory()

    async def only_active_products():
        return [product]

    async def only_active_regions():
        return [region]

    with (
        patch("app.collectors.wb.WbCollector.collect", return_value=obs),
        patch.object(ProductRepository, "list_active", side_effect=only_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", side_effect=only_active_regions, autospec=False),
    ):
        summary = await run_once(factory, settings, mode=RunMode.MANUAL, interactive=False)

    async with factory() as verify_session:
        queue_result = await verify_session.execute(
            select(MeasureQueueItem).where(
                MeasureQueueItem.run_id == summary.run_id,
                MeasureQueueItem.product_id == product.id,
                MeasureQueueItem.region_id == region.id,
            )
        )
        queue_item = queue_result.scalar_one()

        attempt_result = await verify_session.execute(
            select(Attempt).where(Attempt.queue_id == queue_item.id)
        )
        attempt = attempt_result.scalar_one()
        assert attempt.outcome == Outcome.OK

        snapshot_result = await verify_session.execute(
            select(PriceSnapshot).where(
                PriceSnapshot.run_id == summary.run_id,
                PriceSnapshot.product_id == product.id,
                PriceSnapshot.region_id == region.id,
            )
        )
        snapshot = snapshot_result.scalar_one()
        assert snapshot.price == Decimal("100.00")


async def test_run_once_retries_bounded_by_retry_limit(session: AsyncSession) -> None:
    from app.collectors.wb import WbCollectionError
    from app.scheduler.runner import run_once

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="runner-test-sku-ban", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="runner-test-region-ban", name="R", geo={"wb": {"dest": 1}})
    await session.commit()

    settings = Settings(max_concurrency=1, retry_limit=3, queue_claim_batch=10, retry_backoff_base_s=0.0)
    factory = _session_factory()

    async def only_active_products():
        return [product]

    async def only_active_regions():
        return [region]

    def _always_ban(*args, **kwargs):
        raise WbCollectionError("banned", status_code=403)

    with (
        patch("app.collectors.wb.WbCollector.collect", side_effect=_always_ban),
        patch.object(ProductRepository, "list_active", side_effect=only_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", side_effect=only_active_regions, autospec=False),
    ):
        summary = await run_once(factory, settings, mode=RunMode.MANUAL, interactive=False)

    async with factory() as verify_session:
        queue_result = await verify_session.execute(
            select(MeasureQueueItem).where(
                MeasureQueueItem.run_id == summary.run_id,
                MeasureQueueItem.product_id == product.id,
                MeasureQueueItem.region_id == region.id,
            )
        )
        queue_item = queue_result.scalar_one()

        attempt_result = await verify_session.execute(
            select(Attempt).where(Attempt.queue_id == queue_item.id)
        )
        attempts = attempt_result.scalars().all()
        assert len(attempts) == settings.retry_limit
        assert all(a.outcome == Outcome.HARD_BAN for a in attempts)


async def test_run_once_artificial_ban_reflected_in_metrics_and_fires_alert(
    session: AsyncSession,
) -> None:
    """Retried bans show up as ban_rate > 0 / attempts_per_success > 1, and the alerter fires once."""
    from app.collectors.wb import WbCollectionError
    from app.obs.alerts import Alert
    from app.scheduler.runner import run_once

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="runner-test-sku-alert", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="runner-test-region-alert", name="R", geo={"wb": {"dest": 1}})
    await session.commit()

    settings = Settings(
        max_concurrency=1,
        retry_limit=3,
        queue_claim_batch=10,
        retry_backoff_base_s=0.0,
        success_rate_threshold=0.9,
        alert_min_measures=1,
    )
    factory = _session_factory()

    async def only_active_products():
        return [product]

    async def only_active_regions():
        return [region]

    def _always_ban(*args, **kwargs):
        raise WbCollectionError("banned", status_code=403)

    sent_alerts: list[Alert] = []

    class _SpyAlerter:
        async def send(self, alert: Alert) -> None:
            sent_alerts.append(alert)

    with (
        patch("app.collectors.wb.WbCollector.collect", side_effect=_always_ban),
        patch.object(ProductRepository, "list_active", side_effect=only_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", side_effect=only_active_regions, autospec=False),
        patch("app.scheduler.runner.make_alerter", return_value=_SpyAlerter()),
    ):
        summary = await run_once(factory, settings, mode=RunMode.MANUAL, interactive=False)

    assert summary.metrics is not None
    assert summary.metrics.ban_rate > 0
    assert summary.metrics.attempts_per_success > 1
    assert len(sent_alerts) == 1
    assert sent_alerts[0].run_id == summary.run_id


async def test_run_once_success_at_threshold_does_not_fire_alert(session: AsyncSession) -> None:
    from app.obs.alerts import Alert
    from app.scheduler.runner import run_once

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="runner-test-sku-ok-alert", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="runner-test-region-ok-alert", name="R", geo={"wb": {"dest": 1}})
    await session.commit()

    obs = PriceObservation(
        price=Decimal("100.00"),
        price_base=Decimal("100.00"),
        price_card=None,
        currency="RUB",
        is_available=True,
    )

    settings = Settings(
        max_concurrency=1,
        retry_limit=1,
        queue_claim_batch=10,
        success_rate_threshold=0.9,
        alert_min_measures=1,
    )
    factory = _session_factory()

    async def only_active_products():
        return [product]

    async def only_active_regions():
        return [region]

    sent_alerts: list[Alert] = []

    class _SpyAlerter:
        async def send(self, alert: Alert) -> None:
            sent_alerts.append(alert)

    with (
        patch("app.collectors.wb.WbCollector.collect", return_value=obs),
        patch.object(ProductRepository, "list_active", side_effect=only_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", side_effect=only_active_regions, autospec=False),
        patch("app.scheduler.runner.make_alerter", return_value=_SpyAlerter()),
    ):
        summary = await run_once(factory, settings, mode=RunMode.MANUAL, interactive=False)

    assert summary.metrics is not None
    assert summary.metrics.success_rate == 1.0
    assert len(sent_alerts) == 0
