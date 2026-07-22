"""Async repositories for reference-data tables (idempotent upserts) and run/snapshot writes."""

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import PriceObservation
from app.enums import Marketplace, RunMode, RunStatus
from app.models import PriceSnapshot, Product, Region, Run


class ProductRepository:
    """Repository for the `products` reference table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        marketplace: Marketplace,
        sku: str,
        url: str,
        name: str,
        is_active: bool = True,
    ) -> Product:
        """Insert or update a product, keyed on (marketplace, sku)."""
        stmt = (
            insert(Product)
            .values(marketplace=marketplace, sku=sku, url=url, name=name, is_active=is_active)
            .on_conflict_do_update(
                index_elements=[Product.marketplace, Product.sku],
                set_={"url": url, "name": name, "is_active": is_active},
            )
            .returning(Product)
        )
        result = await self._session.execute(stmt, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def list_active(self) -> list[Product]:
        """Return all active products."""
        result = await self._session.execute(select(Product).where(Product.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_by_sku(self, *, marketplace: Marketplace, sku: str) -> Product | None:
        """Look up a single active product by (marketplace, sku)."""
        result = await self._session.execute(
            select(Product).where(
                Product.marketplace == marketplace,
                Product.sku == sku,
                Product.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


class RegionRepository:
    """Repository for the `regions` reference table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        code: str,
        name: str,
        geo: dict[str, Any],
        is_active: bool = True,
    ) -> Region:
        """Insert or update a region, keyed on code."""
        stmt = (
            insert(Region)
            .values(code=code, name=name, geo=geo, is_active=is_active)
            .on_conflict_do_update(
                index_elements=[Region.code],
                set_={"name": name, "geo": geo, "is_active": is_active},
            )
            .returning(Region)
        )
        result = await self._session.execute(stmt, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def list_active(self) -> list[Region]:
        """Return all active regions."""
        result = await self._session.execute(select(Region).where(Region.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Region | None:
        """Look up a single region by code."""
        result = await self._session.execute(select(Region).where(Region.code == code))
        return result.scalar_one_or_none()


class RunRepository:
    """Repository for the `runs` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, mode: RunMode) -> Run:
        """Start a new run in `running` status."""
        run = Run(mode=mode, status=RunStatus.RUNNING)
        self._session.add(run)
        await self._session.flush()
        return run

    async def finish(self, run: Run, status: RunStatus, stats: dict[str, Any]) -> Run:
        """Mark a run finished with the given status and stats."""
        run.status = status
        run.stats = stats
        run.finished_at = datetime.datetime.now(datetime.UTC)
        await self._session.flush()
        return run


class PriceSnapshotRepository:
    """Repository for the insert-only `price_snapshots` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, *, product_id: int, region_id: int, run_id: int, obs: PriceObservation
    ) -> PriceSnapshot:
        """Insert a price snapshot from a parsed observation."""
        snapshot = PriceSnapshot(
            product_id=product_id,
            region_id=region_id,
            run_id=run_id,
            price=obs.price,
            price_base=obs.price_base,
            price_card=obs.price_card,
            currency=obs.currency,
            is_available=obs.is_available,
            raw=obs.raw,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot
