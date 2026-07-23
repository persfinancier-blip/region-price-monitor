"""`ozon` script — measure current Ozon prices across regions (ADR-0008).

Wraps `measure_pair` (`app/collectors/measure.py`) for the Ozon marketplace,
reproducing the former `app/cli.py::_measure_ozon` behaviour exactly:
interactive cookie-warming keyed on `sys.stdin.isatty()`, the "needs warm —
skipped" path when non-interactive and cookies are stale/missing, same DB
writes, same stdout lines, same stats aggregation. Standalone args mirror the
`measure-ozon` CLI command: `--region` (repeatable, default all active
regions with an Ozon geo entry), `--sku` (default all active Ozon products).
"""

import argparse
import asyncio
import sys

from app.collectors.measure import measure_pair
from app.collectors.ozon import OzonCollector
from app.collectors.wb import WbCollector
from app.config import Settings, get_settings
from app.cookies.base import CookieStore
from app.cookies.fs import make_cookie_store
from app.cookies.warm import CookieWarmer, warm_if_stale
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.proxy.base import ProxyProvider
from app.proxy.static import make_proxy_provider
from app.scheduler.runner import SessionFactory
from app.storage.factory import make_storage


async def run(
    region_codes: list[str] | None,
    sku: str | None,
    *,
    session_factory: SessionFactory | None = None,
    settings: Settings | None = None,
    provider: ProxyProvider | None = None,
    cookie_store: CookieStore | None = None,
    wb_collector: WbCollector | None = None,
    ozon_collector: OzonCollector | None = None,
    interactive: bool | None = None,
) -> int:
    """Measure current Ozon prices for the given regions/SKU (default: all active with Ozon geo).

    Reproduces the former CLI `measure-ozon` handler exactly, including the
    interactive cookie-warming branch (keyed on `sys.stdin.isatty()` unless
    overridden) and the `outcome is None` -> "needs warm — skipped" path.
    """
    settings = settings or get_settings()
    session_factory = session_factory or make_storage(settings)
    cookie_store = cookie_store or make_cookie_store(settings)
    wb_collector = wb_collector or WbCollector()
    ozon_collector = ozon_collector or OzonCollector(cookie_store)
    provider = provider or make_proxy_provider(settings)
    interactive = sys.stdin.isatty() if interactive is None else interactive

    async with session_factory() as storage:
        if region_codes:
            regions = []
            for code in region_codes:
                region = await storage.regions.get_by_code(code)
                if region is None:
                    print(f"unknown region: {code}", file=sys.stderr)
                    return 1
                regions.append(region)
        else:
            regions = [r for r in await storage.regions.list_active() if "ozon" in r.geo]

        if sku is not None:
            product = await storage.products.get_by_sku(marketplace=Marketplace.OZON, sku=sku)
            if product is None:
                print(f"unknown Ozon product: {sku}", file=sys.stderr)
                return 1
            products = [product]
        else:
            products = [p for p in await storage.products.list_active() if p.marketplace == Marketplace.OZON]

        run_row = await storage.runs.create(mode=RunMode.MANUAL)

        stats: dict[str, int] = {}
        for product in products:
            for region in regions:
                if interactive:
                    lease = await provider.acquire(region.code)
                    warm_if_stale(
                        cookie_store,
                        CookieWarmer(),
                        Marketplace.OZON,
                        region,
                        settings.ozon_cookie_ttl_hours,
                        lease.proxy_url,
                    )

                queue_item = await storage.queue_items.create(
                    run_id=run_row.id, product_id=product.id, region_id=region.id
                )

                outcome = await measure_pair(
                    run_id=run_row.id,
                    product=product,
                    region=region,
                    provider=provider,
                    wb_collector=wb_collector,
                    ozon_collector=ozon_collector,
                    cookie_store=cookie_store,
                    settings=settings,
                    interactive=interactive,
                    queue_id=queue_item.id,
                    snapshot_repo=storage.snapshots,
                    attempt_repo=storage.attempts,
                )

                if outcome is None:
                    print(f"  sku={product.sku} region={region.code}: needs warm — skipped")
                    await storage.queue_items.mark(queue_item, QueueStatus.FAILED)
                    continue

                await storage.queue_items.mark(
                    queue_item, QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                )

                stats[outcome.value] = stats.get(outcome.value, 0) + 1
                print(f"  sku={product.sku} region={region.code}: {outcome.value}")

        await storage.runs.finish(run_row, RunStatus.DONE, stats)
        await storage.commit()

    print(f"run {run_row.id}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint mirroring the `measure-ozon` CLI command's argv surface."""
    parser = argparse.ArgumentParser(prog="app.scripts.ozon", description="Measure current Ozon prices")
    parser.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )
    parser.add_argument("--sku", default=None, help="Ozon SKU; default: all active Ozon products")
    args = parser.parse_args(argv)

    return asyncio.run(run(args.region, args.sku))


if __name__ == "__main__":
    raise SystemExit(main())
