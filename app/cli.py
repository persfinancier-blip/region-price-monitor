"""Command-line entrypoint for region-price-monitor.

Thin shell (ADR-0008): every subcommand delegates to a script under
`app/scripts/` and only parses args / formats output. No business logic lives
here — see `app/scripts/*.py` for the wrapped implementations.
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.collectors.ozon import OzonCollector
from app.collectors.wb import WbCollector
from app.config import get_settings
from app.db import get_session
from app.db import healthcheck as db_healthcheck
from app.enums import RunMode
from app.models import Run
from app.obs.logging import configure_logging
from app.obs.metrics import compute_run_metrics, to_prometheus
from app.scheduler.runner import Scheduler
from app.scripts import ozon as ozon_script
from app.scripts import wb as wb_script


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
    import json

    from app.enums import Marketplace
    from app.repositories import ProductRepository

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
    import json

    from app.repositories import RegionRepository

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
    from app.cookies.fs import make_cookie_store
    from app.proxy.static import make_proxy_provider

    settings = get_settings()
    cookie_store = make_cookie_store(settings)
    return await wb_script.run(
        region_codes,
        sku,
        session_factory=get_session,
        settings=settings,
        provider=make_proxy_provider(settings),
        cookie_store=cookie_store,
        wb_collector=WbCollector(),
        ozon_collector=OzonCollector(cookie_store),
    )


async def _warm_ozon(region_codes: list[str] | None) -> int:
    from app.cookies.fs import make_cookie_store
    from app.cookies.warm import CookieWarmer, warm_if_stale
    from app.enums import Marketplace
    from app.proxy.static import make_proxy_provider
    from app.repositories import RegionRepository

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
    from app.cookies.fs import make_cookie_store
    from app.proxy.static import make_proxy_provider

    settings = get_settings()
    store = make_cookie_store(settings)
    provider = make_proxy_provider(settings)
    return await ozon_script.run(
        region_codes,
        sku,
        session_factory=get_session,
        settings=settings,
        provider=provider,
        cookie_store=store,
        wb_collector=WbCollector(),
        ozon_collector=OzonCollector(store),
    )


async def _run_once() -> int:
    from app.scripts import orchestrator

    settings = get_settings()
    summary = await orchestrator.run(
        mode=RunMode.MANUAL, interactive=sys.stdin.isatty(), session_factory=get_session, settings=settings
    )
    print(f"run {summary.run_id}: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.stats.items())))
    return 0


async def _metrics(run_id: int | None, last: bool) -> int:
    async with get_session() as session:
        if last:
            result = await session.execute(select(Run).order_by(Run.id.desc()).limit(1))
            run = result.scalar_one_or_none()
            if run is None:
                print("no runs found", file=sys.stderr)
                return 1
            target_run_id = run.id
        elif run_id is not None:
            target_run_id = run_id
        else:
            print("either --run or --last is required", file=sys.stderr)
            return 1

        metrics = await compute_run_metrics(session, target_run_id)

    print(
        f"run {metrics.run_id}: total={metrics.total} "
        f"success_rate={metrics.success_rate:.3f} ban_rate={metrics.ban_rate:.3f} "
        f"error_rate={metrics.error_rate:.3f} avg_duration_ms={metrics.avg_duration_ms:.1f} "
        f"attempts_per_success={metrics.attempts_per_success:.2f}"
    )
    print(to_prometheus(metrics), end="")
    logging.getLogger(__name__).info(
        "metrics",
        extra={
            "run_id": metrics.run_id,
            "total": metrics.total,
            "success_rate": metrics.success_rate,
            "ban_rate": metrics.ban_rate,
            "error_rate": metrics.error_rate,
            "avg_duration_ms": metrics.avg_duration_ms,
            "attempts_per_success": metrics.attempts_per_success,
        },
    )
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

    metrics_parser = subparsers.add_parser(
        "metrics", help="Print a run's metrics (human summary + Prometheus text)"
    )
    metrics_group = metrics_parser.add_mutually_exclusive_group(required=True)
    metrics_group.add_argument("--run", type=int, default=None, dest="run_id", help="Run id")
    metrics_group.add_argument("--last", action="store_true", help="Most recent run")

    args = parser.parse_args(argv)

    configure_logging(get_settings())

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
    if args.command == "metrics":
        return asyncio.run(_metrics(args.run_id, args.last))

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
