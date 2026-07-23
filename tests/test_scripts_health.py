"""app.scripts.health — unit tests over stubbed proxy-health/cookie-store, no DB/Playwright."""

import datetime
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.cookies.base import CookieBundle
from app.enums import Marketplace
from app.proxy.health import HealthVerdict, ProxyHealthService
from app.repositories import RegionRepository
from app.scripts import health


class _FakeRegion:
    def __init__(self, code: str, geo: dict) -> None:
        self.code = code
        self.geo = geo


@asynccontextmanager
async def _fake_session():
    yield object()


class _FakeCookieStore:
    def __init__(self, bundle: CookieBundle | None) -> None:
        self._bundle = bundle
        self.saved: list[CookieBundle] = []

    def load(self, marketplace: Marketplace, region_code: str) -> CookieBundle | None:
        return self._bundle

    def save(self, bundle: CookieBundle) -> None:
        self.saved.append(bundle)

    def mark_stale(self, marketplace: Marketplace, region_code: str) -> None:
        pass


class _FakeWarmer:
    def __init__(self) -> None:
        self.warmed: list[tuple[Marketplace, str]] = []

    def warm(self, marketplace: Marketplace, region, proxy_url=None) -> CookieBundle:
        self.warmed.append((marketplace, region.code))
        return CookieBundle(
            marketplace=marketplace,
            region_code=region.code,
            storage_state={},
            warmed_at=datetime.datetime.now(datetime.UTC),
            stale=False,
        )


async def test_run_reports_unhealthy_on_stale_cookie() -> None:
    msk = _FakeRegion("msk", geo={"ozon": {"city": "Moscow"}})

    async def list_active_regions(self):
        return [msk]

    async def _verdict(self, region_code, proxy_ref):
        return HealthVerdict(cooling_down=False, until=None, ban_count=0)

    with (
        patch.object(RegionRepository, "list_active", list_active_regions, autospec=False),
        patch.object(ProxyHealthService, "verdict", _verdict, autospec=False),
    ):
        report = await health.run(
            fix=False,
            session_factory=_fake_session,
            cookie_store=_FakeCookieStore(bundle=None),
            warmer=_FakeWarmer(),
        )

    assert report.healthy is False
    assert report.regions[0].cookie_stale is True
    assert report.regions[0].warmed is False


async def test_run_fix_triggers_warming_of_stale_cookie() -> None:
    msk = _FakeRegion("msk", geo={"ozon": {"city": "Moscow"}})
    warmer = _FakeWarmer()

    async def list_active_regions(self):
        return [msk]

    async def _verdict(self, region_code, proxy_ref):
        return HealthVerdict(cooling_down=False, until=None, ban_count=0)

    with (
        patch.object(RegionRepository, "list_active", list_active_regions, autospec=False),
        patch.object(ProxyHealthService, "verdict", _verdict, autospec=False),
    ):
        report = await health.run(
            fix=True,
            session_factory=_fake_session,
            cookie_store=_FakeCookieStore(bundle=None),
            warmer=warmer,
        )

    assert report.healthy is True
    assert report.regions[0].warmed is True
    assert warmer.warmed == [(Marketplace.OZON, "msk")]


async def test_run_reports_cooling_down_proxy_unhealthy() -> None:
    fresh_bundle = CookieBundle(
        marketplace=Marketplace.OZON,
        region_code="msk",
        storage_state={},
        warmed_at=datetime.datetime.now(datetime.UTC),
        stale=False,
    )
    msk = _FakeRegion("msk", geo={"ozon": {"city": "Moscow"}})

    async def list_active_regions(self):
        return [msk]

    async def _verdict(self, region_code, proxy_ref):
        return HealthVerdict(cooling_down=False, until=None, ban_count=0)

    with (
        patch.object(RegionRepository, "list_active", list_active_regions, autospec=False),
        patch.object(ProxyHealthService, "verdict", _verdict, autospec=False),
    ):
        report = await health.run(
            fix=False,
            session_factory=_fake_session,
            cookie_store=_FakeCookieStore(bundle=fresh_bundle),
            warmer=_FakeWarmer(),
        )

    assert report.healthy is True


def test_main_help_smoke() -> None:
    with pytest.raises(SystemExit) as exc_info:
        health.main(["--help"])
    assert exc_info.value.code == 0
