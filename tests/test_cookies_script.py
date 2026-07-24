"""app.scripts.cookies — unit tests over a stub warmer, no network, no real browser."""

import datetime
from unittest.mock import patch

from app.config import Settings
from app.cookies.base import CookieBundle
from app.cookies.fs import FsCookieStore
from app.cookies.warm import WalkStepResult
from app.enums import Marketplace
from app.scripts import cities as cities_store
from app.scripts import cookies as cookies_script


def _cities_config() -> cities_store.CitiesConfig:
    config = cities_store.CitiesConfig(
        defaults={
            "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
        },
        cities=[],
    )
    config = cities_store.add_city(config, code="msk", name="Москва", geo={"ozon": {"city": "Москва"}})
    config = cities_store.add_city(config, code="spb", name="Санкт-Петербург", geo={"ozon": {"city": "СПб"}})
    return config


def _stub_warm_all(store, marketplace, walk_cities, *, cancel=None, on_progress=None, launch_browser=None):
    results = []
    if marketplace is Marketplace.WB:
        store.save(
            CookieBundle(
                marketplace=marketplace,
                region_code="_session",
                storage_state={"cookies": []},
                warmed_at=datetime.datetime.now(datetime.UTC),
            )
        )
        results.append(WalkStepResult("_session", "saved"))
        if on_progress:
            on_progress("_session", "saved")
        return results

    for city in walk_cities:
        store.save(
            CookieBundle(
                marketplace=marketplace,
                region_code=city.code,
                storage_state={"cookies": [{"name": "city", "value": city.code}]},
                warmed_at=datetime.datetime.now(datetime.UTC),
            )
        )
        results.append(WalkStepResult(city.code, "saved"))
        if on_progress:
            on_progress(city.code, "saved")
    return results


async def test_collect_ozon_saves_a_bundle_per_city(tmp_path) -> None:
    settings = Settings(
        city_config_path=str(tmp_path / "cities.json"), cookie_store_dir=str(tmp_path / "cookies")
    )
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch.object(cookies_script, "warm_all", _stub_warm_all):
        codes = await cookies_script.collect(Marketplace.OZON, settings=settings, store=store)

    assert set(codes) == {"msk", "spb"}
    assert store.load(Marketplace.OZON, "msk") is not None
    assert store.load(Marketplace.OZON, "spb") is not None


async def test_collect_wb_saves_a_single_session_bundle(tmp_path) -> None:
    settings = Settings(
        city_config_path=str(tmp_path / "cities.json"), cookie_store_dir=str(tmp_path / "cookies")
    )
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch.object(cookies_script, "warm_all", _stub_warm_all):
        codes = await cookies_script.collect(Marketplace.WB, settings=settings, store=store)

    assert codes == ["_session"]
    assert store.load(Marketplace.WB, "_session") is not None
    assert store.load(Marketplace.WB, "msk") is None


async def test_status_reports_valid_expiring_stale_boundaries(tmp_path) -> None:
    settings = Settings(
        city_config_path=str(tmp_path / "cities.json"),
        cookie_store_dir=str(tmp_path / "cookies"),
        ozon_cookie_ttl_hours=12,
    )
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    now = datetime.datetime.now(datetime.UTC)
    store.save(CookieBundle(marketplace=Marketplace.OZON, region_code="msk", storage_state={}, warmed_at=now))
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="spb",
            storage_state={},
            warmed_at=now - datetime.timedelta(hours=11),
        )
    )
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="_session",
            storage_state={},
            warmed_at=now - datetime.timedelta(hours=13),
        )
    )

    reports = await cookies_script.status(Marketplace.OZON, settings=settings, store=store)
    by_code = {r.region_code: r.status for r in reports}

    assert by_code["msk"] == "valid"
    assert by_code["spb"] == "expiring"
    assert by_code["_session"] == "stale"


async def test_set_manual_and_clear_round_trip(tmp_path) -> None:
    settings = Settings(
        city_config_path=str(tmp_path / "cities.json"), cookie_store_dir=str(tmp_path / "cookies")
    )
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    cookies_script.set_manual(
        Marketplace.OZON, "msk", {"cookies": [{"name": "a", "value": "b"}]}, settings=settings, store=store
    )
    bundle = store.load(Marketplace.OZON, "msk")
    assert bundle is not None
    assert bundle.storage_state == {"cookies": [{"name": "a", "value": "b"}]}
    assert bundle.source_ref == "manual"

    cookies_script.clear(Marketplace.OZON, "msk", settings=settings, store=store)
    cleared = store.load(Marketplace.OZON, "msk")
    assert cleared is not None
    assert cleared.stale is True
