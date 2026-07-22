"""Command-line entrypoint for region-price-monitor."""

import argparse
import asyncio
import json
import sys
import time

import requests

from app.collectors.outcome import classify_outcome
from app.collectors.wb import WbCollectionError, WbCollector
from app.config import get_settings
from app.db import get_session
from app.db import healthcheck as db_healthcheck
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.proxy.static import make_proxy_provider
from app.repositories import (
    AttemptRepository,
    MeasureQueueRepository,
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


async def _measure_wb(region_codes: list[str] | None, sku: str | None) -> int:
    collector = WbCollector()
    settings = get_settings()
    provider = make_proxy_provider(settings)

    async with get_session() as session:
        region_repo = RegionRepository(session)
        product_repo = ProductRepository(session)
        run_repo = RunRepository(session)
        snapshot_repo = PriceSnapshotRepository(session)
        queue_repo = MeasureQueueRepository(session)
        attempt_repo = AttemptRepository(session)

        if region_codes:
            regions = []
            for code in region_codes:
                region = await region_repo.get_by_code(code)
                if region is None:
                    print(f"unknown region: {code}", file=sys.stderr)
                    return 1
                regions.append(region)
        else:
            regions = await region_repo.list_active()

        if sku is not None:
            product = await product_repo.get_by_sku(marketplace=Marketplace.WB, sku=sku)
            if product is None:
                print(f"unknown WB product: {sku}", file=sys.stderr)
                return 1
            products = [product]
        else:
            products = [p for p in await product_repo.list_active() if p.marketplace == Marketplace.WB]

        run = await run_repo.create(mode=RunMode.MANUAL)

        stats: dict[str, int] = {}
        for product in products:
            for region in regions:
                queue_item = await queue_repo.create(
                    run_id=run.id, product_id=product.id, region_id=region.id
                )
                lease = await provider.acquire(region.code)

                started = time.monotonic()
                status_code: int | None = None
                empty_products = False
                error: str | None = None
                obs = None
                exc_for_timeout: Exception | None = None
                try:
                    obs = await asyncio.to_thread(collector.collect, product, region, lease.proxy_url)
                    status_code = 200
                except WbCollectionError as exc:
                    status_code = exc.status_code
                    empty_products = exc.empty_products
                    error = str(exc)
                except requests.Timeout as exc:
                    exc_for_timeout = exc
                    error = str(exc)
                except Exception as exc:  # noqa: BLE001 — classified below, never aborts the run
                    exc_for_timeout = exc
                    error = str(exc)
                duration_ms = int((time.monotonic() - started) * 1000)

                outcome = classify_outcome(
                    status_code=status_code, exc=exc_for_timeout, empty_products=empty_products
                )

                if outcome == Outcome.OK and obs is not None:
                    await snapshot_repo.add(
                        product_id=product.id, region_id=region.id, run_id=run.id, obs=obs
                    )

                await attempt_repo.add(
                    queue_id=queue_item.id,
                    proxy_ref=lease.ref,
                    outcome=outcome,
                    duration_ms=duration_ms,
                    error=error,
                )
                await queue_repo.mark(
                    queue_item, QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                )
                await provider.report(lease, outcome)

                stats[outcome.value] = stats.get(outcome.value, 0) + 1
                print(f"  sku={product.sku} region={region.code}: {outcome.value}")

        await run_repo.finish(run, RunStatus.DONE, stats)
        await session.commit()

    print(f"run {run.id}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="region-price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Verify DB connectivity")

    import_products = subparsers.add_parser("import-products", help="Upsert products from a JSON file")
    import_products.add_argument("file", help="Path to a products JSON file")

    import_regions = subparsers.add_parser("import-regions", help="Upsert regions from a JSON file")
    import_regions.add_argument("file", help="Path to a regions JSON file")

    measure_wb = subparsers.add_parser(
        "measure-wb", help="Measure current WB prices across regions (via ProxyProvider)"
    )
    measure_wb.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions)",
    )
    measure_wb.add_argument("--sku", default=None, help="WB SKU (nm); default: all active WB products")

    args = parser.parse_args(argv)

    if args.command == "healthcheck":
        return asyncio.run(_run_healthcheck())
    if args.command == "import-products":
        return asyncio.run(_import_products(args.file))
    if args.command == "import-regions":
        return asyncio.run(_import_regions(args.file))
    if args.command == "measure-wb":
        return asyncio.run(_measure_wb(args.region, args.sku))

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
