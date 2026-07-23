"""app.scripts.export — unit tests over stubbed storage/sink, no DB."""

import datetime
from contextlib import asynccontextmanager
from decimal import Decimal

from app.config import Settings
from app.scripts import export


class _FakeProduct:
    def __init__(self, id_: int, marketplace, sku: str, url: str, name: str) -> None:
        self.id = id_
        self.marketplace = marketplace
        self.sku = sku
        self.url = url
        self.name = name


class _FakeRegion:
    def __init__(self, id_: int, code: str) -> None:
        self.id = id_
        self.code = code


class _FakeSnapshot:
    def __init__(self, product_id: int, region_id: int) -> None:
        self.product_id = product_id
        self.region_id = region_id
        self.captured_at = datetime.datetime(2026, 7, 23, tzinfo=datetime.UTC)
        self.price = Decimal("199.90")
        self.price_base = Decimal("219.90")
        self.price_card = Decimal("189.90")
        self.currency = "RUB"
        self.is_available = True


class _FakeMarketplace:
    value = "wb"


class _FakeStorage:
    def __init__(self, snapshots, products, regions) -> None:
        self.snapshots = _FakeSnapshotRepo(snapshots)
        self.products = _FakeProductRepo(products)
        self.regions = _FakeRegionRepo(regions)


class _FakeSnapshotRepo:
    def __init__(self, snapshots) -> None:
        self._snapshots = snapshots

    async def list_all(self):
        return self._snapshots


class _FakeProductRepo:
    def __init__(self, products) -> None:
        self._products = products

    async def list_active(self):
        return self._products


class _FakeRegionRepo:
    def __init__(self, regions) -> None:
        self._regions = regions

    async def list_active(self):
        return self._regions


class _FakeSink:
    def __init__(self) -> None:
        self.written: list[dict] = []

    async def write_snapshots(self, rows):
        self.written = rows
        return len(rows)


def _storage_factory(snapshots, products, regions):
    @asynccontextmanager
    async def _factory():
        yield _FakeStorage(snapshots, products, regions)

    return _factory


async def test_run_builds_canonical_rows_and_writes_through_sink() -> None:
    product = _FakeProduct(1, _FakeMarketplace(), "12345", "https://x/1", "Товар А")
    region = _FakeRegion(1, "msk")
    snapshot = _FakeSnapshot(product_id=1, region_id=1)
    sink = _FakeSink()

    result = await export.run(sink=sink, storage_factory=_storage_factory([snapshot], [product], [region]))

    assert result == 0
    assert sink.written == [
        {
            "marketplace": "wb",
            "sku": "12345",
            "url": "https://x/1",
            "name": "Товар А",
            "region": "msk",
            "price": "199.90",
            "price_no_card": "219.90",
            "price_card": "189.90",
            "currency": "RUB",
            "availability": True,
            "measured_at": "2026-07-23T00:00:00+00:00",
            "status": "ok",
        }
    ]


async def test_run_preview_prints_and_does_not_write(capsys) -> None:
    product = _FakeProduct(1, _FakeMarketplace(), "12345", "https://x/1", "Товар А")
    region = _FakeRegion(1, "msk")
    snapshot = _FakeSnapshot(product_id=1, region_id=1)
    sink = _FakeSink()

    result = await export.run(
        preview=True, sink=sink, storage_factory=_storage_factory([snapshot], [product], [region])
    )

    assert result == 0
    assert sink.written == []
    assert "12345" in capsys.readouterr().out


async def test_run_no_sink_configured_is_a_clean_noop(tmp_path, capsys) -> None:
    settings = Settings(io_config_path=str(tmp_path / "does-not-exist.json"))

    result = await export.run(settings=settings, storage_factory=_storage_factory([], [], []))

    assert result == 0
    assert "no sink configured" in capsys.readouterr().out


def test_main_help_smoke() -> None:
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        export.main(["--help"])
    assert exc_info.value.code == 0
