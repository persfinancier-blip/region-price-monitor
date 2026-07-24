"""app.panel — cities block: dashboard renders it, POST /cities* mutate the local store."""

import contextlib
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.enums import RunMode, RunStatus
from app.obs.metrics import RunMetrics
from app.panel import app as panel_app
from app.scripts import cities as cities_store
from app.scripts import control_panel


@dataclass
class _FakeRun:
    id: int
    mode: RunMode
    status: RunStatus
    started_at: str = "2026-07-24T10:00:00Z"
    finished_at: str | None = "2026-07-24T10:05:00Z"


@asynccontextmanager
async def _fake_session():
    yield object()


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


async def _fake_recent_runs(storage, limit=10):
    return [_FakeRun(id=1, mode=RunMode.MANUAL, status=RunStatus.DONE)]


async def _fake_latest_snapshots(storage):
    return []


async def _fake_compute_run_metrics(storage, run_id):
    return RunMetrics(run_id=run_id, total=0, by_outcome={}, success_rate=0.0)


async def _fake_control_panel_run(*args, **kwargs):
    return control_panel.WorkSet(pairs=[], cities=[])


def _settings(tmp_path):
    return Settings(city_config_path=str(tmp_path / "cities.json"))


@contextlib.contextmanager
def _dashboard_patches(settings):
    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
        patch("app.panel.app.queries.recent_runs", _fake_recent_runs),
        patch("app.panel.app.queries.latest_snapshots", _fake_latest_snapshots),
        patch("app.panel.app.compute_run_metrics", _fake_compute_run_metrics),
        patch.object(control_panel, "run", _fake_control_panel_run),
    ):
        yield


def test_dashboard_renders_interactive_cities_block(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    cities_store.save(config, settings)

    with _dashboard_patches(settings):
        response = _client().get("/")

    assert response.status_code == 200
    assert "Москва" in response.text
    assert "Добавить город" in response.text


def test_post_cities_adds_city(tmp_path) -> None:
    settings = _settings(tmp_path)
    cities_store.save(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        settings,
    )

    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
    ):
        response = _client().post(
            "/cities",
            data={"code": "spb", "name": "Санкт-Петербург", "geo_ozon": "SPB"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    with open(settings.city_config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    codes = [c["code"] for c in raw["cities"]]
    assert "spb" in codes


def test_post_marketplace_sets_override_and_persists(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    cities_store.save(config, settings)

    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
    ):
        response = _client().post(
            "/cities/msk/ozon",
            data={
                "mode": "override",
                "enabled": "true",
                "proxy": "http://user:pass@proxy.example",
                "interval_min": "120",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    with open(settings.city_config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    msk = next(c for c in raw["cities"] if c["code"] == "msk")
    assert msk["ozon"]["mode"] == "override"
    assert msk["ozon"]["enabled"] is True
    assert msk["ozon"]["proxy"] == "http://user:pass@proxy.example"
    assert msk["ozon"]["interval_min"] == 120


def test_post_marketplace_inherit_mode(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    config = cities_store.set_marketplace(
        config, code="msk", marketplace="wb", mode="override", enabled=True, proxy="http://p", interval_min=60
    )
    cities_store.save(config, settings)

    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
    ):
        response = _client().post(
            "/cities/msk/wb",
            data={"mode": "inherit", "enabled": "false", "proxy": "", "interval_min": "360"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    with open(settings.city_config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    msk = next(c for c in raw["cities"] if c["code"] == "msk")
    assert msk["wb"]["mode"] == "inherit"


def test_post_marketplace_empty_proxy_keeps_stored_value(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    config = cities_store.set_marketplace(
        config,
        code="msk",
        marketplace="wb",
        mode="override",
        enabled=True,
        proxy="http://real",
        interval_min=60,
    )
    cities_store.save(config, settings)

    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
    ):
        response = _client().post(
            "/cities/msk/wb",
            data={"mode": "override", "enabled": "true", "proxy": "", "interval_min": "60"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    with open(settings.city_config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    msk = next(c for c in raw["cities"] if c["code"] == "msk")
    assert msk["wb"]["proxy"] == "http://real"


def test_post_delete_deactivates_city(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    cities_store.save(config, settings)

    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.get_settings", return_value=settings),
    ):
        response = _client().post("/cities/msk/delete", follow_redirects=False)

    assert response.status_code == 303
    with open(settings.city_config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw["cities"] == []


def test_dashboard_masks_proxy_in_cities_block(tmp_path) -> None:
    settings = _settings(tmp_path)
    config = cities_store.add_city(
        cities_store.CitiesConfig(
            defaults={
                "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
                "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            },
            cities=[],
        ),
        code="msk",
        name="Москва",
    )
    config = cities_store.set_marketplace(
        config,
        code="msk",
        marketplace="ozon",
        mode="override",
        enabled=True,
        proxy="http://user:pass@proxy.example",
        interval_min=90,
    )
    cities_store.save(config, settings)

    with _dashboard_patches(settings):
        response = _client().get("/")

    assert "user:pass" not in response.text
