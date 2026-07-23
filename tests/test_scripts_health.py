"""app.scripts.health — unit tests over stubbed proxy-health/cookie-store, no DB/Playwright."""

import datetime
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.cookies.base import CookieBundle
from app.enums import Marketplace
from app.proxy.health import HealthVerdict, ProxyHealthService
from app.scripts import health
from app.storage.local import LocalRegionRepository


class _FakeRegion:
    def __init__(self, code: str, geo: dict) -> None:
        self.code = code
        self.geo = geo


class _FakeStorage:
    def __init__(self) -> None:
        self.regions = LocalRegionRepository.__new__(LocalRegionRepository)

    async def commit(self) -> None:
        pass


@asynccontextmanager
async def _fake_session():
    yield _FakeStorage()


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
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
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
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
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
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
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


class _FakeLease:
    def __init__(self, proxy_url: str | None) -> None:
        self.proxy_url = proxy_url


class _FakeProvider:
    def __init__(self) -> None:
        self.acquired: list[str] = []

    async def acquire(self, region_code: str) -> _FakeLease:
        self.acquired.append(region_code)
        return _FakeLease(proxy_url=None)


async def test_warm_warms_all_ozon_regions_by_default(capsys) -> None:
    msk = _FakeRegion("msk", geo={"ozon": {"city": "Moscow"}})
    spb = _FakeRegion("spb", geo={})  # no ozon geo — excluded from default
    warmer = _FakeWarmer()
    provider = _FakeProvider()

    async def list_active_regions(self):
        return [msk, spb]

    with patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False):
        result = await health.warm(
            None,
            session_factory=_fake_session,
            cookie_store=_FakeCookieStore(bundle=None),
            provider=provider,
            warmer=warmer,
        )

    assert result == 0
    assert warmer.warmed == [(Marketplace.OZON, "msk")]
    assert "region=msk: warmed" in capsys.readouterr().out


async def test_warm_unknown_region_exits_1() -> None:
    async def get_by_code(self, code: str):
        return None

    with patch.object(LocalRegionRepository, "get_by_code", get_by_code, autospec=False):
        result = await health.warm(
            ["nowhere"],
            session_factory=_fake_session,
            cookie_store=_FakeCookieStore(bundle=None),
            provider=_FakeProvider(),
            warmer=_FakeWarmer(),
        )

    assert result == 1


def test_main_dispatches_warm() -> None:
    with patch.object(health, "warm") as mock_warm:

        async def _noop(*args, **kwargs):
            return 0

        mock_warm.side_effect = _noop
        result = health.main(["warm", "--region", "msk"])

    assert result == 0
    mock_warm.assert_called_once_with(["msk"])
