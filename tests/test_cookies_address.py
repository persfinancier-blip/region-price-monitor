"""Ozon address-memory model (ADR-0013): guided capture, auto-refresh by remembered label.

No network, no real browser — `warm_all` is stubbed to simulate the guided-capture and
auto-select outcomes the real Playwright walk would produce.
"""

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


def _stub_guided_warm_all(
    store, marketplace, walk_cities, *, cancel=None, on_progress=None, launch_browser=None
):
    """Simulates guided capture — every walked city gets a freshly captured address label."""
    results = []
    if marketplace is Marketplace.WB:
        store.save(
            CookieBundle(
                marketplace=marketplace,
                region_code="_session",
                storage_state={"cookies": []},
                warmed_at=datetime.datetime.now(datetime.UTC),
                address_label=None,
            )
        )
        results.append(WalkStepResult("_session", "saved"))
        if on_progress:
            on_progress("_session", "saved")
        return results

    for city in walk_cities:
        label = f"Адрес, {city.name}"
        store.save(
            CookieBundle(
                marketplace=marketplace,
                region_code=city.code,
                storage_state={"cookies": [{"name": "city", "value": city.code}]},
                warmed_at=datetime.datetime.now(datetime.UTC),
                address_label=label,
            )
        )
        results.append(WalkStepResult(city.code, "saved", address_label=label))
        if on_progress:
            on_progress(city.code, "saved")
    return results


def _stub_refresh_warm_all(
    store, marketplace, walk_cities, *, cancel=None, on_progress=None, launch_browser=None
):
    """Simulates auto-refresh — only re-saves cities that already carry a remembered label."""
    results = []
    for city in walk_cities:
        assert city.address_label, "refresh must only be called with cities that have a remembered address"
        store.save(
            CookieBundle(
                marketplace=marketplace,
                region_code=city.code,
                storage_state={"cookies": [{"name": "city", "value": city.code, "refreshed": True}]},
                warmed_at=datetime.datetime.now(datetime.UTC),
                address_label=city.address_label,
            )
        )
        results.append(WalkStepResult(city.code, "saved", address_label=city.address_label))
        if on_progress:
            on_progress(city.code, "saved")
    return results


def _settings(tmp_path) -> Settings:
    return Settings(
        city_config_path=str(tmp_path / "cities.json"),
        cookie_store_dir=str(tmp_path / "cookies"),
        ozon_cookie_ttl_hours=12,
    )


async def test_guided_collect_records_address_label_per_ozon_city(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch.object(cookies_script, "warm_all", _stub_guided_warm_all):
        codes = await cookies_script.collect(Marketplace.OZON, settings=settings, store=store)

    assert set(codes) == {"msk", "spb"}
    msk = store.load(Marketplace.OZON, "msk")
    spb = store.load(Marketplace.OZON, "spb")
    assert msk is not None and msk.address_label == "Адрес, Москва"
    assert spb is not None and spb.address_label == "Адрес, Санкт-Петербург"


async def test_collect_skips_cities_that_already_have_a_remembered_address(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="msk",
            storage_state={"cookies": []},
            warmed_at=datetime.datetime.now(datetime.UTC),
            address_label="Уже запомненный адрес",
        )
    )

    with patch.object(cookies_script, "warm_all", _stub_guided_warm_all):
        codes = await cookies_script.collect(Marketplace.OZON, settings=settings, store=store)

    assert codes == ["spb"]
    msk = store.load(Marketplace.OZON, "msk")
    assert msk is not None and msk.address_label == "Уже запомненный адрес"


async def test_collect_force_recaptures_every_city(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="msk",
            storage_state={"cookies": []},
            warmed_at=datetime.datetime.now(datetime.UTC),
            address_label="Старый адрес",
        )
    )

    with patch.object(cookies_script, "warm_all", _stub_guided_warm_all):
        codes = await cookies_script.collect(Marketplace.OZON, settings=settings, store=store, force=True)

    assert set(codes) == {"msk", "spb"}
    msk = store.load(Marketplace.OZON, "msk")
    assert msk is not None and msk.address_label == "Адрес, Москва"


async def test_refresh_auto_selects_remembered_label_for_stale_cities_only(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)
    now = datetime.datetime.now(datetime.UTC)
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="msk",
            storage_state={"cookies": []},
            warmed_at=now - datetime.timedelta(hours=13),  # stale, TTL=12h
            address_label="Москва, адрес",
        )
    )
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="spb",
            storage_state={"cookies": []},
            warmed_at=now,  # fresh — refresh must not touch it
            address_label="СПб, адрес",
        )
    )

    with patch.object(cookies_script, "warm_all", _stub_refresh_warm_all):
        codes = await cookies_script.refresh(Marketplace.OZON, settings=settings, store=store)

    assert codes == ["msk"]
    msk = store.load(Marketplace.OZON, "msk")
    spb = store.load(Marketplace.OZON, "spb")
    assert msk is not None and msk.storage_state["cookies"][0].get("refreshed") is True
    assert spb is not None and spb.storage_state["cookies"] == []


async def test_refresh_skips_cities_with_no_remembered_address(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="msk",
            storage_state={"cookies": []},
            warmed_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=13),
            address_label=None,
        )
    )

    with patch.object(cookies_script, "warm_all", _stub_refresh_warm_all):
        codes = await cookies_script.refresh(Marketplace.OZON, settings=settings, store=store)

    assert codes == []


async def test_refresh_wb_still_saves_a_single_session_bundle_without_address(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(_cities_config(), settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch.object(cookies_script, "warm_all", _stub_guided_warm_all):
        codes = await cookies_script.refresh(Marketplace.WB, settings=settings, store=store)

    assert codes == ["_session"]
    bundle = store.load(Marketplace.WB, "_session")
    assert bundle is not None and bundle.address_label is None
