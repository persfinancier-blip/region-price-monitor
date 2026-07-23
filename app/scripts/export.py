"""`export` script — write `price_snapshots` (+ product/region) through the configured sink (ADR-0010).

Reads all snapshots via the storage seam, joins product/region by id, builds
canonical result rows (SPEC-panel §7), and writes them through
`make_result_sink(settings)`. `price_snapshots` is insert-only and only ever
holds successful reads, so exported rows always carry `status: "ok"`.
`--preview` prints the first mapped rows instead of writing.
"""

import argparse
import asyncio
from typing import Any

from app.config import Settings, get_settings
from app.io.base import ResultSink
from app.io.factory import make_result_sink
from app.storage.factory import StorageFactory, make_storage


async def _build_result_rows(storage_factory: StorageFactory) -> list[dict[str, Any]]:
    async with storage_factory() as storage:
        snapshots = await storage.snapshots.list_all()
        products = {p.id: p for p in await storage.products.list_active()}
        regions = {r.id: r for r in await storage.regions.list_active()}

    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        product = products.get(snapshot.product_id)
        region = regions.get(snapshot.region_id)
        rows.append(
            {
                "marketplace": product.marketplace.value if product else None,
                "sku": product.sku if product else None,
                "url": product.url if product else None,
                "name": product.name if product else None,
                "region": region.code if region else None,
                "price": str(snapshot.price),
                "price_no_card": str(snapshot.price_base),
                "price_card": str(snapshot.price_card) if snapshot.price_card is not None else None,
                "currency": snapshot.currency,
                "availability": snapshot.is_available,
                "measured_at": snapshot.captured_at.isoformat(),
                "status": "ok",
            }
        )
    return rows


async def run(
    *,
    preview: bool = False,
    sink: ResultSink | None = None,
    storage_factory: StorageFactory | None = None,
    settings: Settings | None = None,
) -> int:
    """Build canonical result rows and write them through the configured sink.

    `--preview` prints the first rows instead of writing. With no sink
    configured, exits cleanly stating so (local-first default, ADR-0009).
    """
    settings = settings or get_settings()
    storage_factory = storage_factory or make_storage(settings)
    rows = await _build_result_rows(storage_factory)

    if preview:
        for row in rows[:5]:
            print(row)
        return 0

    sink = sink if sink is not None else make_result_sink(settings)
    if sink is None:
        print("no sink configured (settings.io_config_path); nothing written")
        return 0

    written = await sink.write_snapshots(rows)
    print(f"wrote {written} row(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `python -m app.scripts.export [--preview]`."""
    parser = argparse.ArgumentParser(
        prog="app.scripts.export", description="Write price snapshots through the configured result sink"
    )
    parser.add_argument(
        "--preview", action="store_true", help="Print the first mapped rows instead of writing"
    )
    args = parser.parse_args(argv)

    return asyncio.run(run(preview=args.preview))


if __name__ == "__main__":
    raise SystemExit(main())
