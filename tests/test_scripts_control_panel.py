"""app.scripts.control_panel — unit tests over stubbed repositories, no DB."""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

from app.config import Settings
from app.enums import Marketplace
from app.scripts import control_panel
from app.storage.local import LocalProductRepository, LocalRegionRepository


class _FakeProduct:
    def __init__(self, id_: int, marketplace: Marketplace, sku: str) -> None:
        self.id = id_
        self.marketplace = marketplace
        self.sku = sku


class _FakeRegion:
    def __init__(self, id_: int, code: str, geo: dict) -> None:
        self.id = id_
        self.code = code
        self.geo = geo


class _FakeStorage:
    def __init__(self) -> None:
        self.products = LocalProductRepository.__new__(LocalProductRepository)
        self.regions = LocalRegionRepository.__new__(LocalRegionRepository)

    async def commit(self) -> None:
        pass


@asynccontextmanager
async def _fake_session():
    yield _FakeStorage()


@asynccontextmanager
async def _fake_committable_session():
    yield _FakeStorage()


async def test_run_mirrors_active_pairs_semantics() -> None:
    """WB pairs with all active regions; Ozon only with regions carrying an `ozon` geo entry."""
    wb_product = _FakeProduct(1, Marketplace.WB, "wb-sku")
    ozon_product = _FakeProduct(2, Marketplace.OZON, "ozon-sku")
    msk = _FakeRegion(1, "msk", geo={"wb": {"dest": 1}, "ozon": {"city": "Moscow"}})
    spb = _FakeRegion(2, "spb", geo={"wb": {"dest": 2}})  # no ozon geo

    async def list_active_products(self):
        return [wb_product, ozon_product]

    async def list_active_regions(self):
        return [msk, spb]

    with (
        patch.object(LocalProductRepository, "list_active", list_active_products, autospec=False),
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
    ):
        work_set = await control_panel.run(_fake_session, Settings())

    pair_keys = {(p.sku, r.code, mp) for p, r, mp in work_set.pairs}
    assert pair_keys == {
        ("wb-sku", "msk", Marketplace.WB),
        ("wb-sku", "spb", Marketplace.WB),
        ("ozon-sku", "msk", Marketplace.OZON),
    }

    cities_by_code = {c.region.code: c for c in work_set.cities}
    assert cities_by_code["msk"].marketplaces == (Marketplace.OZON, Marketplace.WB)
    assert cities_by_code["spb"].marketplaces == (Marketplace.WB,)


async def test_format_report_masks_proxy_ref() -> None:
    settings = Settings(proxy_map_json='{"msk": "http://user:pass@proxy.example:8080"}')
    msk = _FakeRegion(1, "msk", geo={"wb": {"dest": 1}})

    async def list_active_products(self):
        return []

    async def list_active_regions(self):
        return [msk]

    with (
        patch.object(LocalProductRepository, "list_active", list_active_products, autospec=False),
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
    ):
        work_set = await control_panel.run(_fake_session, settings)

    report = control_panel.format_report(work_set)

    assert "user:pass" not in report
    assert "proxy=***" in report


def test_main_help_smoke() -> None:
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        control_panel.main(["--help"])
    assert exc_info.value.code == 0


async def test_import_products_reports_imported_and_updated(tmp_path, capsys) -> None:
    existing = _FakeProduct(1, Marketplace.WB, "existing-sku")

    async def list_active_products(self):
        return [existing]

    upserted = []

    async def upsert(self, *, marketplace, sku, url, name):
        upserted.append((marketplace, sku))
        return _FakeProduct(len(upserted), marketplace, sku)

    path = tmp_path / "products.json"
    path.write_text(
        json.dumps(
            [
                {"marketplace": "wb", "sku": "existing-sku", "url": "https://x/1", "name": "A"},
                {"marketplace": "wb", "sku": "new-sku", "url": "https://x/2", "name": "B"},
            ]
        )
    )

    with (
        patch.object(LocalProductRepository, "list_active", list_active_products, autospec=False),
        patch.object(LocalProductRepository, "upsert", upsert, autospec=False),
    ):
        result = await control_panel.import_products(str(path), storage_factory=_fake_committable_session)

    assert result == 0
    assert upserted == [(Marketplace.WB, "existing-sku"), (Marketplace.WB, "new-sku")]
    assert "imported 1 / updated 1" in capsys.readouterr().out


async def test_import_regions_reports_imported_and_updated(tmp_path, capsys) -> None:
    existing = _FakeRegion(1, "msk", geo={})

    async def list_active_regions(self):
        return [existing]

    upserted = []

    async def upsert(self, *, code, name, geo):
        upserted.append(code)
        return _FakeRegion(len(upserted), code, geo)

    path = tmp_path / "regions.json"
    path.write_text(
        json.dumps(
            [
                {"code": "msk", "name": "Moscow", "geo": {}},
                {"code": "spb", "name": "SPB", "geo": {}},
            ]
        )
    )

    with (
        patch.object(LocalRegionRepository, "list_active", list_active_regions, autospec=False),
        patch.object(LocalRegionRepository, "upsert", upsert, autospec=False),
    ):
        result = await control_panel.import_regions(str(path), storage_factory=_fake_committable_session)

    assert result == 0
    assert upserted == ["msk", "spb"]
    assert "imported 1 / updated 1" in capsys.readouterr().out


def test_main_dispatches_import_products(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text("[]")

    with patch.object(control_panel, "import_products") as mock_import:

        async def _noop(*args, **kwargs):
            return 0

        mock_import.side_effect = _noop
        result = control_panel.main(["import-products", str(path)])

    assert result == 0
    mock_import.assert_called_once_with(str(path))


def test_main_dispatches_import_regions(tmp_path) -> None:
    path = tmp_path / "regions.json"
    path.write_text("[]")

    with patch.object(control_panel, "import_regions") as mock_import:

        async def _noop(*args, **kwargs):
            return 0

        mock_import.side_effect = _noop
        result = control_panel.main(["import-regions", str(path)])

    assert result == 0
    mock_import.assert_called_once_with(str(path))
