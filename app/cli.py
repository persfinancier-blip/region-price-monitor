"""Command-line entrypoint for region-price-monitor."""

import argparse
import asyncio
import json
import sys

from app.db import get_session
from app.db import healthcheck as db_healthcheck
from app.enums import Marketplace
from app.repositories import ProductRepository, RegionRepository


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="region-price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Verify DB connectivity")

    import_products = subparsers.add_parser("import-products", help="Upsert products from a JSON file")
    import_products.add_argument("file", help="Path to a products JSON file")

    import_regions = subparsers.add_parser("import-regions", help="Upsert regions from a JSON file")
    import_regions.add_argument("file", help="Path to a regions JSON file")

    args = parser.parse_args(argv)

    if args.command == "healthcheck":
        return asyncio.run(_run_healthcheck())
    if args.command == "import-products":
        return asyncio.run(_import_products(args.file))
    if args.command == "import-regions":
        return asyncio.run(_import_regions(args.file))

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
