"""app.panel — Куки tab: renders buttons + health table, collect job + manual set/clear."""

import datetime
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.cookies.base import CookieBundle
from app.cookies.fs import FsCookieStore
from app.enums import Marketplace
from app.panel import app as panel_app
from app.scripts import cities as cities_store


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


def _settings(tmp_path) -> Settings:
    return Settings(
        city_config_path=str(tmp_path / "cities.json"), cookie_store_dir=str(tmp_path / "cookies")
    )


def _seed_city(settings: Settings) -> None:
    config = cities_store.CitiesConfig(
        defaults={
            "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
        },
        cities=[],
    )
    config = cities_store.add_city(config, code="msk", name="Москва")
    cities_store.save(config, settings)


def test_cookies_tab_renders_buttons_and_health_table(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_city(settings)
    store = FsCookieStore(settings.cookie_store_dir)
    store.save(
        CookieBundle(
            marketplace=Marketplace.OZON,
            region_code="msk",
            storage_state={},
            warmed_at=datetime.datetime.now(datetime.UTC),
            address_label="Москва, ул. Примерная, 1",
        )
    )

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().get("/tab/cookies")

    assert response.status_code == 200
    assert "Авторизоваться и собрать" in response.text
    assert "Обновить протухшие" in response.text
    assert "Москва" in response.text
    assert "валидна" in response.text
    assert "Москва, ул. Примерная, 1" in response.text


def test_post_collect_starts_job_and_status_reflects_progress(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_city(settings)

    async def _fake_collect(marketplace, *, settings=None, store=None, cancel=None, on_progress=None):
        if on_progress:
            on_progress("msk", "saved")
        return ["msk"]

    with (
        patch("app.panel.app.get_settings", return_value=settings),
        patch("app.panel.app.cookies_script.collect", _fake_collect),
    ):
        client = _client()
        response = client.post("/cookies/ozon/collect")
        assert response.status_code == 200
        assert "Сбор запущен" in response.text

        for _ in range(50):
            status_response = client.get("/cookies/status")
            job = status_response.json()["ozon"]
            if not job["running"] and job["steps"]:
                break
            time.sleep(0.02)

    assert job["steps"] == [{"city_code": "msk", "status": "saved", "detail": None}]


def test_post_manual_cookie_sets_and_clear_drops_it(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_city(settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/cookies/ozon/msk",
            data={"raw": '{"cookies": [{"name": "a", "value": "b"}]}'},
            follow_redirects=False,
        )
    assert response.status_code == 303
    bundle = store.load(Marketplace.OZON, "msk")
    assert bundle is not None
    assert bundle.storage_state == {"cookies": [{"name": "a", "value": "b"}]}

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post("/cookies/ozon/msk/clear", follow_redirects=False)
    assert response.status_code == 303
    cleared = store.load(Marketplace.OZON, "msk")
    assert cleared is not None
    assert cleared.stale is True


def test_post_manual_cookie_sets_address_label(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_city(settings)
    store = FsCookieStore(settings.cookie_store_dir)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/cookies/ozon/msk",
            data={"raw": '{"cookies": []}', "address_label": "Москва, ул. Примерная, 1"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    bundle = store.load(Marketplace.OZON, "msk")
    assert bundle is not None
    assert bundle.address_label == "Москва, ул. Примерная, 1"


def test_post_refresh_starts_job_and_status_reflects_progress(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_city(settings)

    async def _fake_refresh(marketplace, *, settings=None, store=None, cancel=None, on_progress=None):
        if on_progress:
            on_progress("msk", "saved")
        return ["msk"]

    with (
        patch("app.panel.app.get_settings", return_value=settings),
        patch("app.panel.app.cookies_script.refresh", _fake_refresh),
    ):
        client = _client()
        response = client.post("/cookies/ozon/refresh")
        assert response.status_code == 200
        assert "Обновление запущено" in response.text

        for _ in range(50):
            status_response = client.get("/cookies/status")
            job = status_response.json()["ozon"]
            if not job["running"] and job["steps"]:
                break
            time.sleep(0.02)

    assert job["steps"] == [{"city_code": "msk", "status": "saved", "detail": None}]
