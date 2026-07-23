"""Read-only query helpers for the panel Dashboard (ADR-0008: panel is a shell, no writes).

Wraps `RunRepository`/models with the extra read shapes the Dashboard needs
(recent runs list, latest price snapshot per product×region). Never mutates.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceSnapshot, Product, Region, Run
from app.repositories import RunRepository


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
    captured_at: object


async def recent_runs(session: AsyncSession, limit: int = 10) -> list[Run]:
    """Return the last `limit` runs, most recent first."""
    return await RunRepository(session).list_recent(limit)


async def latest_snapshots(session: AsyncSession) -> list[LatestSnapshot]:
    """Return the most recent `PriceSnapshot` per (product, region), newest capture first."""
    stmt = (
        select(PriceSnapshot, Product, Region)
        .join(Product, PriceSnapshot.product_id == Product.id)
        .join(Region, PriceSnapshot.region_id == Region.id)
        .where(
            PriceSnapshot.id
            == (
                select(PriceSnapshot.id)
                .where(
                    PriceSnapshot.product_id == Product.id,
                    PriceSnapshot.region_id == Region.id,
                )
                .order_by(PriceSnapshot.captured_at.desc())
                .limit(1)
                .correlate(Product, Region)
                .scalar_subquery()
            )
        )
        .order_by(PriceSnapshot.captured_at.desc())
    )
    result = await session.execute(stmt)

    return [
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
        for snapshot, product, region in result.all()
    ]
