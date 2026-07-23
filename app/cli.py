"""Command-line entrypoint for region-price-monitor."""

import argparse
import asyncio
import json
import sys

from app.collectors.measure import measure_pair
from app.collectors.ozon import OzonCollector
from app.collectors.wb import WbCollector
from app.config import get_settings
from app.cookies.fs import make_cookie_store
from app.cookies.warm import CookieWarmer, warm_if_stale
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
from app.scheduler.runner import Scheduler, run_once


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
    settings = get_settings()
    provider = make_proxy_provider(settings)
    cookie_store = make_cookie_store(settings)
    wb_collector = WbCollector()
    ozon_collector = OzonCollector(cookie_store)

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

                outcome = await measure_pair(
                    run_id=run.id,
                    product=product,
                    region=region,
                    provider=provider,
                    wb_collector=wb_collector,
                    ozon_collector=ozon_collector,
                    cookie_store=cookie_store,
                    settings=settings,
                    interactive=False,
                    queue_id=queue_item.id,
                    snapshot_repo=snapshot_repo,
                    attempt_repo=attempt_repo,
                )
                assert outcome is not None  # WB never returns the Ozon "needs warm" sentinel

                await queue_repo.mark(
                    queue_item, QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                )

                stats[outcome.value] = stats.get(outcome.value, 0) + 1
                print(f"  sku={product.sku} region={region.code}: {outcome.value}")

        await run_repo.finish(run, RunStatus.DONE, stats)
        await session.commit()

    print(f"run {run.id}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 0


async def _warm_ozon(region_codes: list[str] | None) -> int:
    settings = get_settings()
    store = make_cookie_store(settings)
    warmer = CookieWarmer()
    provider = make_proxy_provider(settings)

    async with get_session() as session:
        region_repo = RegionRepository(session)
        if region_codes:
            regions = []
            for code in region_codes:
                region = await region_repo.get_by_code(code)
                if region is None:
                    print(f"unknown region: {code}", file=sys.stderr)
                    return 1
                regions.append(region)
        else:
            regions = [r for r in await region_repo.list_active() if "ozon" in r.geo]

    for region in regions:
        lease = await provider.acquire(region.code)
        warm_if_stale(
            store, warmer, Marketplace.OZON, region, settings.ozon_cookie_ttl_hours, lease.proxy_url
        )
        print(f"  region={region.code}: warmed")
    return 0


async def _measure_ozon(region_codes: list[str] | None, sku: str | None) -> int:
    settings = get_settings()
    store = make_cookie_store(settings)
    wb_collector = WbCollector()
    ozon_collector = OzonCollector(store)
    provider = make_proxy_provider(settings)
    interactive = sys.stdin.isatty()

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
            regions = [r for r in await region_repo.list_active() if "ozon" in r.geo]

        if sku is not None:
            product = await product_repo.get_by_sku(marketplace=Marketplace.OZON, sku=sku)
            if product is None:
                print(f"unknown Ozon product: {sku}", file=sys.stderr)
                return 1
            products = [product]
        else:
            products = [p for p in await product_repo.list_active() if p.marketplace == Marketplace.OZON]

        run = await run_repo.create(mode=RunMode.MANUAL)

        stats: dict[str, int] = {}
        for product in products:
            for region in regions:
                if interactive:
                    lease = await provider.acquire(region.code)
                    warm_if_stale(
                        store,
                        CookieWarmer(),
                        Marketplace.OZON,
                        region,
                        settings.ozon_cookie_ttl_hours,
                        lease.proxy_url,
                    )

                queue_item = await queue_repo.create(
                    run_id=run.id, product_id=product.id, region_id=region.id
                )

                outcome = await measure_pair(
                    run_id=run.id,
                    product=product,
                    region=region,
                    provider=provider,
                    wb_collector=wb_collector,
                    ozon_collector=ozon_collector,
                    cookie_store=store,
                    settings=settings,
                    interactive=interactive,
                    queue_id=queue_item.id,
                    snapshot_repo=snapshot_repo,
                    attempt_repo=attempt_repo,
                )

                if outcome is None:
                    print(f"  sku={product.sku} region={region.code}: needs warm — skipped")
                    await queue_repo.mark(queue_item, QueueStatus.FAILED)
                    continue

                await queue_repo.mark(
                    queue_item, QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                )

                stats[outcome.value] = stats.get(outcome.value, 0) + 1
                print(f"  sku={product.sku} region={region.code}: {outcome.value}")

        await run_repo.finish(run, RunStatus.DONE, stats)
        await session.commit()

    print(f"run {run.id}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 0


async def _run_once() -> int:
    settings = get_settings()
    summary = await run_once(get_session, settings, mode=RunMode.MANUAL, interactive=sys.stdin.isatty())
    print(f"run {summary.run_id}: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.stats.items())))
    return 0


async def _serve() -> int:
    settings = get_settings()
    scheduler = Scheduler(get_session, settings)
    scheduler.start()
    print(f"scheduler running, cron={settings.schedule_cron} (Ctrl-C to stop)")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scheduler.shutdown()
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

    measure_ozon = subparsers.add_parser(
        "measure-ozon", help="Measure current Ozon prices across regions (via warmed cookies)"
    )
    measure_ozon.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )
    measure_ozon.add_argument("--sku", default=None, help="Ozon SKU; default: all active Ozon products")

    warm_ozon = subparsers.add_parser("warm-ozon", help="Warm Ozon cookies for one or all regions")
    warm_ozon.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )

    subparsers.add_parser(
        "run-once", help="Trigger one full run across all active pairs via Scheduler+Queue+worker pool"
    )
    subparsers.add_parser("serve", help="Start the cron daemon (APScheduler) and block")

    args = parser.parse_args(argv)

    if args.command == "healthcheck":
        return asyncio.run(_run_healthcheck())
    if args.command == "import-products":
        return asyncio.run(_import_products(args.file))
    if args.command == "import-regions":
        return asyncio.run(_import_regions(args.file))
    if args.command == "measure-wb":
        return asyncio.run(_measure_wb(args.region, args.sku))
    if args.command == "measure-ozon":
        return asyncio.run(_measure_ozon(args.region, args.sku))
    if args.command == "warm-ozon":
        return asyncio.run(_warm_ozon(args.region))
    if args.command == "run-once":
        return asyncio.run(_run_once())
    if args.command == "serve":
        return asyncio.run(_serve())

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
