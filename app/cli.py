"""Command-line entrypoint for region-price-monitor."""

import argparse
import asyncio
import json
import sys

from app.collectors.wb import WbCollector
from app.config import get_settings
from app.db import get_session
from app.db import healthcheck as db_healthcheck
from app.enums import Marketplace, RunMode, RunStatus
from app.repositories import (
    PriceSnapshotRepository,
    ProductRepository,
    RegionRepository,
    RunRepository,
)


async def _run_healthcheck() -> int:
    try:
        ok = await db_healthcheck()
    except Exception as exc:  # noqa: BLE001 — surface any connectivity failure to the operator
        print(f"DB healthcheck FAILED: {exc}", file=sys.stderr)
        return 1
    if ok:
        print("OK")
        return 0
    print("DB healthcheck FAILED: unexpected result", file=sys.stderr)
    return 1


async def _import_products(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)

    imported = 0
    updated = 0
    async with get_session() as session:
        repo = ProductRepository(session)
        existing_keys = {(p.marketplace, p.sku) for p in await repo.list_active()}
        for item in items:
            marketplace = Marketplace(item["marketplace"])
            await repo.upsert(marketplace=marketplace, sku=item["sku"], url=item["url"], name=item["name"])
            if (marketplace, item["sku"]) in existing_keys:
                updated += 1
            else:
                imported += 1
        await session.commit()

    print(f"imported {imported} / updated {updated}")
    return 0


async def _import_regions(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)

    imported = 0
    updated = 0
    async with get_session() as session:
        repo = RegionRepository(session)
        existing_codes = {r.code for r in await repo.list_active()}
        for item in items:
            await repo.upsert(code=item["code"], name=item["name"], geo=item["geo"])
            if item["code"] in existing_codes:
                updated += 1
            else:
                imported += 1
        await session.commit()

    print(f"imported {imported} / updated {updated}")
    return 0


async def _measure_wb(region_code: str, sku: str | None) -> int:
    collector = WbCollector()
    async with get_session() as session:
        region_repo = RegionRepository(session)
        product_repo = ProductRepository(session)
        run_repo = RunRepository(session)
        snapshot_repo = PriceSnapshotRepository(session)

        region = await region_repo.get_by_code(region_code)
        if region is None:
            print(f"unknown region: {region_code}", file=sys.stderr)
            return 1

        if sku is not None:
            product = await product_repo.get_by_sku(marketplace=Marketplace.WB, sku=sku)
            if product is None:
                print(f"unknown WB product: {sku}", file=sys.stderr)
                return 1
            products = [product]
        else:
            products = [p for p in await product_repo.list_active() if p.marketplace == Marketplace.WB]

        run = await run_repo.create(mode=RunMode.MANUAL)

        ok = 0
        failed = 0
        for product in products:
            try:
                obs = await asyncio.to_thread(collector.collect, product, region)
            except ValueError as exc:
                print(f"  failed sku={product.sku}: {exc}", file=sys.stderr)
                failed += 1
                continue
            await snapshot_repo.add(product_id=product.id, region_id=region.id, run_id=run.id, obs=obs)
            ok += 1

        await run_repo.finish(run, RunStatus.DONE, {"ok": ok, "failed": failed})
        await session.commit()

    print(f"run {run.id}: measured {ok}, failed {failed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="region-price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Verify DB connectivity")

    import_products = subparsers.add_parser("import-products", help="Upsert products from a JSON file")
    import_products.add_argument("file", help="Path to a products JSON file")

    import_regions = subparsers.add_parser("import-regions", help="Upsert regions from a JSON file")
    import_regions.add_argument("file", help="Path to a regions JSON file")

    measure_wb = subparsers.add_parser("measure-wb", help="Measure current WB prices (home region, no proxy)")
    measure_wb.add_argument("--region", default=None, help="Region code (default: settings.home_region)")
    measure_wb.add_argument("--sku", default=None, help="WB SKU (nm); default: all active WB products")

    args = parser.parse_args(argv)

    if args.command == "healthcheck":
        return asyncio.run(_run_healthcheck())
    if args.command == "import-products":
        return asyncio.run(_import_products(args.file))
    if args.command == "import-regions":
        return asyncio.run(_import_regions(args.file))
    if args.command == "measure-wb":
        region_code = args.region or get_settings().home_region
        return asyncio.run(_measure_wb(region_code, args.sku))

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
