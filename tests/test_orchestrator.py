"""app.scripts.orchestrator — Pipeline mechanism (pure) + DB-backed run() parity with run_once."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import PriceObservation
from app.config import Settings
from app.db import make_engine
from app.enums import Marketplace, RunMode
from app.repositories import ProductRepository, RegionRepository
from app.scripts.orchestrator import Pipeline, Step


async def test_pipeline_executes_steps_in_dependency_order() -> None:
    order: list[str] = []

    async def _a() -> str:
        order.append("a")
        return "a"

    async def _b() -> str:
        order.append("b")
        return "b"

    async def _c() -> str:
        order.append("c")
        return "c"

    # Declared out of dependency order; the pipeline must still run a -> b -> c.
    pipeline = Pipeline(
        steps=(
            Step(name="c", action=_c, needs=("b",)),
            Step(name="a", action=_a),
            Step(name="b", action=_b, needs=("a",)),
        )
    )

    results = await pipeline.run()

    assert order == ["a", "b", "c"]
    assert results == {"a": "a", "b": "b", "c": "c"}


async def test_pipeline_raises_on_cycle() -> None:
    async def _noop() -> None:
        return None

    pipeline = Pipeline(
        steps=(
            Step(name="x", action=_noop, needs=("y",)),
            Step(name="y", action=_noop, needs=("x",)),
        )
    )

    with pytest.raises(ValueError, match="cycle"):
        pipeline.order()


async def test_pipeline_raises_on_unknown_dependency() -> None:
    async def _noop() -> None:
        return None

    pipeline = Pipeline(steps=(Step(name="x", action=_noop, needs=("missing",)),))

    with pytest.raises(ValueError, match="unknown step"):
        pipeline.order()


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


async def test_orchestrator_run_matches_run_once_shape(session: AsyncSession) -> None:
    """orchestrator.run() over stubbed collectors yields the same RunSummary/stats shape as run_once."""
    from app.scripts.orchestrator import run as orchestrator_run

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="orchestrator-test-sku", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="orchestrator-test-region", name="R", geo={"wb": {"dest": 1}})
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
        summary = await orchestrator_run(
            mode=RunMode.MANUAL, interactive=False, session_factory=factory, settings=settings
        )

    assert summary.run_id > 0
    assert summary.stats.get("ok") == 1
    assert summary.metrics is not None
    assert summary.metrics.success_rate == 1.0


async def test_orchestrator_run_artificial_ban_reflected_in_metrics_and_fires_alert(
    session: AsyncSession,
) -> None:
    """The Фаза 6 artificial-ban + alert assertions still hold through the orchestrator path."""
    from app.collectors.wb import WbCollectionError
    from app.obs.alerts import Alert
    from app.scripts.orchestrator import run as orchestrator_run

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB,
        sku="orchestrator-test-sku-alert",
        url="https://example.com/p",
        name="P",
    )
    region = await region_repo.upsert(
        code="orchestrator-test-region-alert", name="R", geo={"wb": {"dest": 1}}
    )
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
        summary = await orchestrator_run(
            mode=RunMode.MANUAL, interactive=False, session_factory=factory, settings=settings
        )

    assert summary.metrics is not None
    assert summary.metrics.ban_rate > 0
    assert summary.metrics.attempts_per_success > 1
    assert len(sent_alerts) == 1
    assert sent_alerts[0].run_id == summary.run_id
