"""app.scripts.control_panel — unit tests over stubbed repositories, no DB."""

from contextlib import asynccontextmanager
from unittest.mock import patch

from app.config import Settings
from app.enums import Marketplace
from app.repositories import ProductRepository, RegionRepository
from app.scripts import control_panel


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


@asynccontextmanager
async def _fake_session():
    yield object()


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
        patch.object(ProductRepository, "list_active", list_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", list_active_regions, autospec=False),
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
        patch.object(ProductRepository, "list_active", list_active_products, autospec=False),
        patch.object(RegionRepository, "list_active", list_active_regions, autospec=False),
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
