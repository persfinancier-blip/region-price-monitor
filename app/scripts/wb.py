"""`wb` script — measure current WB prices across regions (ADR-0008).

Wraps `measure_pair` (`app/collectors/measure.py`) for the WB marketplace,
reproducing the former `app/cli.py::_measure_wb` behaviour exactly: same DB
writes (run/queue/attempt/snapshot), same stdout lines, same stats
aggregation. `run()` is importable (and takes injectable dependencies so the
CLI shell can pass through patchable collaborators); standalone args mirror
the `measure-wb` CLI command: `--region` (repeatable, default all active),
`--sku` (default all active WB products).
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
from app.db import get_session
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.proxy.base import ProxyProvider
from app.proxy.static import make_proxy_provider
from app.repositories import (
    AttemptRepository,
    MeasureQueueRepository,
    PriceSnapshotRepository,
    ProductRepository,
    RegionRepository,
    RunRepository,
)
from app.scheduler.runner import SessionFactory


async def run(
    region_codes: list[str] | None,
    sku: str | None,
    *,
    session_factory: SessionFactory = get_session,
    settings: Settings | None = None,
    provider: ProxyProvider | None = None,
    cookie_store: CookieStore | None = None,
    wb_collector: WbCollector | None = None,
    ozon_collector: OzonCollector | None = None,
) -> int:
    """Measure current WB prices for the given regions/SKU (default: all active).

    Reproduces the former CLI `measure-wb` handler exactly: writes a run,
    per-pair queue items and attempts, a snapshot on success, prints one
    line per pair plus a final summary line, and returns the process exit code.
    """
    settings = settings or get_settings()
    provider = provider or make_proxy_provider(settings)
    cookie_store = cookie_store or make_cookie_store(settings)
    wb_collector = wb_collector or WbCollector()
    ozon_collector = ozon_collector or OzonCollector(cookie_store)

    async with session_factory() as session:
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

        run_row = await run_repo.create(mode=RunMode.MANUAL)

        stats: dict[str, int] = {}
        for product in products:
            for region in regions:
                queue_item = await queue_repo.create(
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

        await run_repo.finish(run_row, RunStatus.DONE, stats)
        await session.commit()

    print(f"run {run_row.id}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint mirroring the `measure-wb` CLI command's argv surface."""
    parser = argparse.ArgumentParser(prog="app.scripts.wb", description="Measure current WB prices")
    parser.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions)",
    )
    parser.add_argument("--sku", default=None, help="WB SKU (nm); default: all active WB products")
    args = parser.parse_args(argv)

    return asyncio.run(run(args.region, args.sku))


if __name__ == "__main__":
    raise SystemExit(main())
