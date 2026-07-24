"""app.panel — `GET /` Dashboard, stubbed queries/metrics/control_panel, no DB."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.enums import RunMode, RunStatus
from app.obs.metrics import RunMetrics
from app.panel import app as panel_app
from app.panel.queries import LatestSnapshot
from app.scripts import cities as cities_store
from app.scripts import control_panel


@dataclass
class _FakeRun:
    id: int
    mode: RunMode
    status: RunStatus
    started_at: str = "2026-07-23T10:00:00Z"
    finished_at: str | None = "2026-07-23T10:05:00Z"


@dataclass
class _FakeRegion:
    code: str


@dataclass
class _FakeCity:
    region: _FakeRegion
    proxy_ref: str | None
    marketplaces: tuple


@dataclass
class _FakeWorkSet:
    pairs: list
    cities: list


@asynccontextmanager
async def _fake_session():
    yield object()


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


async def _fake_recent_runs(session, limit=10):
    return [_FakeRun(id=1, mode=RunMode.MANUAL, status=RunStatus.DONE)]


async def _fake_latest_snapshots(session):
    return [
        LatestSnapshot(
            product_name="Product A",
            marketplace="wb",
            region_code="msk",
            price=Decimal("100.00"),
            price_base=Decimal("120.00"),
            price_card=Decimal("95.00"),
            is_available=True,
            captured_at="2026-07-23T10:04:00Z",
        )
    ]


async def _fake_compute_run_metrics(session, run_id):
    return RunMetrics(run_id=run_id, total=5, by_outcome={"ok": 5}, success_rate=1.0)


async def _fake_control_panel_run(*args, **kwargs):
    return _FakeWorkSet(
        pairs=[],
        cities=[
            _FakeCity(region=_FakeRegion(code="msk"), proxy_ref="http://user:pass@proxy", marketplaces=())
        ],
    )


async def _fake_cities_load(*args, **kwargs):
    return cities_store.CitiesConfig(
        defaults={
            "wb": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            "ozon": cities_store.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
        },
        cities=[],
    )


def test_dashboard_renders_health_runs_prices_cities() -> None:
    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.queries.recent_runs", _fake_recent_runs),
        patch("app.panel.app.queries.latest_snapshots", _fake_latest_snapshots),
        patch("app.panel.app.compute_run_metrics", _fake_compute_run_metrics),
        patch.object(control_panel, "run", _fake_control_panel_run),
        patch.object(cities_store, "load", _fake_cities_load),
    ):
        response = _client().get("/")

    assert response.status_code == 200
    body = response.text
    assert "Product A" in body
    assert "msk" in body
    assert "Запустить сейчас" in body


def test_dashboard_masks_proxy_credentials() -> None:
    with (
        patch("app.panel.app.make_storage", return_value=_fake_session),
        patch("app.panel.app.queries.recent_runs", _fake_recent_runs),
        patch("app.panel.app.queries.latest_snapshots", _fake_latest_snapshots),
        patch("app.panel.app.compute_run_metrics", _fake_compute_run_metrics),
        patch.object(control_panel, "run", _fake_control_panel_run),
        patch.object(cities_store, "load", _fake_cities_load),
    ):
        response = _client().get("/")

    assert "user:pass" not in response.text
    assert "proxy" not in response.text.lower() or "***" in response.text


def test_health_endpoint() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
