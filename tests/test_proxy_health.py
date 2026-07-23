"""evaluate_health (pure) + ProxyHealthService/HealthAwareProxyProvider (DB-gated where noted)."""

import datetime
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import make_engine
from app.enums import Marketplace, Outcome, RunMode
from app.proxy.base import ProxyLease
from app.proxy.health import (
    HealthAwareProxyProvider,
    HealthVerdict,
    ProxyHealthService,
    ProxyOnCooldown,
    evaluate_health,
)
from app.repositories import (
    AttemptRepository,
    MeasureQueueRepository,
    ProductRepository,
    RegionRepository,
    RunRepository,
)
from app.storage.postgres import PostgresStorage

NOW = datetime.datetime(2026, 7, 23, 12, 0, 0, tzinfo=datetime.UTC)


def test_below_threshold_not_cooling() -> None:
    verdict = evaluate_health(2, NOW, NOW, threshold=3, cooldown_s=1800)
    assert verdict == HealthVerdict(cooling_down=False, until=None, ban_count=2)


def test_at_threshold_cooling_until_last_ban_plus_cooldown() -> None:
    last_ban_at = NOW - datetime.timedelta(minutes=5)
    verdict = evaluate_health(3, last_ban_at, NOW, threshold=3, cooldown_s=1800)
    assert verdict.cooling_down is True
    assert verdict.until == last_ban_at + datetime.timedelta(seconds=1800)
    assert verdict.ban_count == 3


def test_above_threshold_cooling() -> None:
    last_ban_at = NOW - datetime.timedelta(minutes=5)
    verdict = evaluate_health(5, last_ban_at, NOW, threshold=3, cooldown_s=1800)
    assert verdict.cooling_down is True


def test_no_last_ban_at_never_cools() -> None:
    verdict = evaluate_health(5, None, NOW, threshold=3, cooldown_s=1800)
    assert verdict.cooling_down is False


def test_boundary_exactly_at_until_not_cooling() -> None:
    last_ban_at = NOW - datetime.timedelta(seconds=1800)
    verdict = evaluate_health(3, last_ban_at, NOW, threshold=3, cooldown_s=1800)
    assert verdict.until == NOW
    assert verdict.cooling_down is False


def test_past_cooldown_window_not_cooling() -> None:
    last_ban_at = NOW - datetime.timedelta(seconds=3600)
    verdict = evaluate_health(3, last_ban_at, NOW, threshold=3, cooldown_s=1800)
    assert verdict.cooling_down is False


async def test_health_aware_provider_raises_on_cooling_service() -> None:
    """Service faked — no DB needed to check the decorator's control flow."""

    class _Base:
        async def acquire(self, region_code: str) -> ProxyLease:
            return ProxyLease(
                provider="static", region_code=region_code, proxy_url=None, ref="static:msk:direct"
            )

        async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
            return None

    class _CoolingHealth:
        async def verdict(self, region_code: str, proxy_ref: str) -> HealthVerdict:
            return HealthVerdict(cooling_down=True, until=NOW, ban_count=3)

    settings = Settings()
    provider = HealthAwareProxyProvider(_Base(), _CoolingHealth(), settings)  # type: ignore[arg-type]

    with pytest.raises(ProxyOnCooldown) as exc_info:
        await provider.acquire("msk")
    assert exc_info.value.region_code == "msk"
    assert exc_info.value.until == NOW


async def test_health_aware_provider_passes_through_when_not_cooling() -> None:
    class _Base:
        async def acquire(self, region_code: str) -> ProxyLease:
            return ProxyLease(
                provider="static", region_code=region_code, proxy_url=None, ref="static:msk:direct"
            )

        async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
            return None

    class _HealthyHealth:
        async def verdict(self, region_code: str, proxy_ref: str) -> HealthVerdict:
            return HealthVerdict(cooling_down=False, until=None, ban_count=0)

    settings = Settings()
    provider = HealthAwareProxyProvider(_Base(), _HealthyHealth(), settings)  # type: ignore[arg-type]

    lease = await provider.acquire("msk")
    assert lease.ref == "static:msk:direct"


async def test_health_aware_provider_fails_open_on_service_error() -> None:
    class _Base:
        async def acquire(self, region_code: str) -> ProxyLease:
            return ProxyLease(
                provider="static", region_code=region_code, proxy_url=None, ref="static:msk:direct"
            )

        async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
            return None

    class _BrokenHealth:
        async def verdict(self, region_code: str, proxy_ref: str) -> HealthVerdict:
            raise RuntimeError("db unreachable")

    settings = Settings()
    provider = HealthAwareProxyProvider(_Base(), _BrokenHealth(), settings)  # type: ignore[arg-type]

    lease = await provider.acquire("msk")
    assert lease.ref == "static:msk:direct"


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

if not TEST_DATABASE_URL:
    pytest.skip("no TEST_DATABASE_URL/DATABASE_URL configured for DB-gated cases", allow_module_level=True)

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

    @asynccontextmanager
    async def _storage_factory():
        async with factory() as sess:
            yield PostgresStorage(sess)

    return _storage_factory


async def test_service_verdict_reads_recent_bans_from_attempts(session: AsyncSession) -> None:
    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)
    queue_repo = MeasureQueueRepository(session)
    attempt_repo = AttemptRepository(session)
    run_repo = RunRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="health-test-sku", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="health-test-region", name="R", geo={"wb": {"dest": 1}})
    run = await run_repo.create(mode=RunMode.MANUAL)
    queue_item = await queue_repo.create(run_id=run.id, product_id=product.id, region_id=region.id)

    proxy_ref = "static:health-test-region:1.2.3.4"
    for _ in range(3):
        await attempt_repo.add(
            queue_id=queue_item.id, proxy_ref=proxy_ref, outcome=Outcome.HARD_BAN, duration_ms=100
        )
    await session.commit()

    settings = Settings(proxy_ban_threshold=3, proxy_health_window_s=900, proxy_cooldown_s=1800)
    service = ProxyHealthService(_session_factory(), settings)

    verdict = await service.verdict(region.code, proxy_ref)
    assert verdict.cooling_down is True
    assert verdict.ban_count == 3
