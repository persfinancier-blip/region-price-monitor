"""Read-only query helpers for the panel Dashboard (ADR-0008: panel is a shell, no writes).

Wraps the storage seam with the extra read shapes the Dashboard needs (recent
runs list, latest price snapshot per product×region). Never mutates.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from app.models import PriceSnapshot, Run
from app.storage.base import Storage


@dataclass(frozen=True)
class LatestSnapshot:
    """The most recent price observation for one (product, region) pair."""

    product_name: str
    marketplace: str
    region_code: str
    price: Decimal
    price_base: Decimal
    price_card: Decimal | None
    is_available: bool
    captured_at: datetime.datetime


async def recent_runs(storage: Storage, limit: int = 10) -> list[Run]:
    """Return the last `limit` runs, most recent first."""
    return await storage.runs.list_recent(limit)


async def latest_snapshots(storage: Storage) -> list[LatestSnapshot]:
    """Return the most recent `PriceSnapshot` per (product, region), newest capture first."""
    all_snapshots = await storage.snapshots.list_all()

    latest_by_pair: dict[tuple[int, int], PriceSnapshot] = {}
    for snapshot in all_snapshots:
        key = (snapshot.product_id, snapshot.region_id)
        current = latest_by_pair.get(key)
        if current is None or snapshot.captured_at > current.captured_at:
            latest_by_pair[key] = snapshot

    results = []
    for (product_id, region_id), snapshot in latest_by_pair.items():
        product = await storage.products.get_by_id(product_id)
        region = await storage.regions.get_by_id(region_id)
        if product is None or region is None:
            continue
        results.append(
            LatestSnapshot(
                product_name=product.name,
                marketplace=product.marketplace.value,
                region_code=region.code,
                price=snapshot.price,
                price_base=snapshot.price_base,
                price_card=snapshot.price_card,
                is_available=snapshot.is_available,
                captured_at=snapshot.captured_at,
            )
        )
    results.sort(key=lambda s: s.captured_at, reverse=True)
    return results
