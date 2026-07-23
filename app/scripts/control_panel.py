"""`control-panel` script — active (product x region) work set + per-city settings (ADR-0008/0009).

Wraps the storage seam's `products`/`regions` repos to yield the same active
work set `app/scheduler/runner.py::_active_pairs` computes (WB: all active
regions; Ozon: only regions with an `"ozon"` geo entry), plus a per-city
settings view (proxy ref masked in the printed output only — the returned
data keeps the real values for downstream scripts).
"""

import argparse
import json
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.enums import Marketplace
from app.models import Product, Region
from app.proxy.static import parse_proxy_map
from app.storage.factory import StorageFactory, make_storage

_MASK = "***"


@dataclass(frozen=True)
class CitySettings:
    """Per-region settings relevant to a measurement run."""

    region: Region
    proxy_ref: str | None
    marketplaces: tuple[Marketplace, ...]


@dataclass(frozen=True)
class WorkSet:
    """The active (product, region, marketplace) triples plus per-city settings."""

    pairs: list[tuple[Product, Region, Marketplace]]
    cities: list[CitySettings]


async def run(storage_factory: StorageFactory | None = None, settings: Settings | None = None) -> WorkSet:
    """Return the active work set, mirroring `_active_pairs` semantics exactly.

    WB: paired with all active regions. Ozon: paired only with active regions
    that carry an `"ozon"` geo entry.
    """
    settings = settings or get_settings()
    storage_factory = storage_factory or make_storage(settings)
    proxy_map = parse_proxy_map(settings.proxy_map_json)
    async with storage_factory() as storage:
        products = await storage.products.list_active()
        regions = await storage.regions.list_active()
        ozon_regions = [r for r in regions if "ozon" in r.geo]

        pairs: list[tuple[Product, Region, Marketplace]] = []
        for product in products:
            target_regions = regions if product.marketplace == Marketplace.WB else ozon_regions
            for region in target_regions:
                pairs.append((product, region, product.marketplace))

        cities = [
            CitySettings(
                region=region,
                proxy_ref=proxy_map.get(region.code, settings.proxy_url),
                marketplaces=tuple(
                    sorted({mp for (_p, r, mp) in pairs if r.id == region.id}, key=lambda m: m.value)
                ),
            )
            for region in regions
        ]

    return WorkSet(pairs=pairs, cities=cities)


async def import_products(
    path: str, *, storage_factory: StorageFactory | None = None, settings: Settings | None = None
) -> int:
    """Upsert products from a JSON file; print `imported <n> / updated <n>`."""
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)

    storage_factory = storage_factory or make_storage(settings or get_settings())
    imported = 0
    updated = 0
    async with storage_factory() as storage:
        existing_keys = {(p.marketplace, p.sku) for p in await storage.products.list_active()}
        for item in items:
            marketplace = Marketplace(item["marketplace"])
            await storage.products.upsert(
                marketplace=marketplace, sku=item["sku"], url=item["url"], name=item["name"]
            )
            if (marketplace, item["sku"]) in existing_keys:
                updated += 1
            else:
                imported += 1
        await storage.commit()

    print(f"imported {imported} / updated {updated}")
    return 0


async def import_regions(
    path: str, *, storage_factory: StorageFactory | None = None, settings: Settings | None = None
) -> int:
    """Upsert regions from a JSON file; print `imported <n> / updated <n>`."""
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)

    storage_factory = storage_factory or make_storage(settings or get_settings())
    imported = 0
    updated = 0
    async with storage_factory() as storage:
        existing_codes = {r.code for r in await storage.regions.list_active()}
        for item in items:
            await storage.regions.upsert(code=item["code"], name=item["name"], geo=item["geo"])
            if item["code"] in existing_codes:
                updated += 1
            else:
                imported += 1
        await storage.commit()

    print(f"imported {imported} / updated {updated}")
    return 0


def format_report(work_set: WorkSet) -> str:
    """Render the active cities + settings, proxy refs masked."""
    lines = [f"active pairs: {len(work_set.pairs)}"]
    for city in work_set.cities:
        proxy_display = _MASK if city.proxy_ref else None
        marketplaces = ",".join(m.value for m in city.marketplaces) or "-"
        lines.append(f"  region={city.region.code} proxy={proxy_display} marketplaces={marketplaces}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `show` (default) prints the work set; `import-products`/
    `import-regions <file>` upsert from a JSON file."""
    import asyncio

    parser = argparse.ArgumentParser(
        prog="app.scripts.control_panel", description="Print the active (product x region) work set"
    )
    subparsers = parser.add_subparsers(dest="action")
    subparsers.add_parser("show", help="Print the active (product x region) work set (default)")
    import_products_parser = subparsers.add_parser("import-products", help="Upsert products from a JSON file")
    import_products_parser.add_argument("file", help="Path to a products JSON file")
    import_regions_parser = subparsers.add_parser("import-regions", help="Upsert regions from a JSON file")
    import_regions_parser.add_argument("file", help="Path to a regions JSON file")

    args = parser.parse_args(argv)

    if args.action == "import-products":
        return asyncio.run(import_products(args.file))
    if args.action == "import-regions":
        return asyncio.run(import_regions(args.file))

    work_set = asyncio.run(run())
    print(format_report(work_set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
