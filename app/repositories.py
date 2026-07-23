"""Async repositories for reference-data tables (idempotent upserts) and run/snapshot writes."""

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import PriceObservation
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.models import Attempt, MeasureQueueItem, PriceSnapshot, Product, Region, Run


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

    async def get_by_id(self, product_id: int) -> Product | None:
        """Look up a single product by id."""
        return await self._session.get(Product, product_id)


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

    async def get_by_id(self, region_id: int) -> Region | None:
        """Look up a single region by id."""
        return await self._session.get(Region, region_id)


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

    async def get(self, run_id: int) -> Run | None:
        """Look up a single run by id."""
        return await self._session.get(Run, run_id)

    async def list_recent(self, limit: int = 10) -> list[Run]:
        """Return the last `limit` runs, most recent first."""
        result = await self._session.execute(select(Run).order_by(Run.id.desc()).limit(limit))
        return list(result.scalars().all())

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

    async def list_all(self) -> list[PriceSnapshot]:
        """Return every snapshot (panel Dashboard's latest-per-pair reduction runs in Python)."""
        result = await self._session.execute(select(PriceSnapshot))
        return list(result.scalars().all())


class MeasureQueueRepository:
    """Repository for the `measure_queue` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, run_id: int, product_id: int, region_id: int) -> MeasureQueueItem:
        """Insert a pending (run, product, region) queue item."""
        item = MeasureQueueItem(
            run_id=run_id, product_id=product_id, region_id=region_id, status=QueueStatus.PENDING
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def mark(self, item: MeasureQueueItem, status: QueueStatus) -> MeasureQueueItem:
        """Update a queue item's status."""
        item.status = status
        await self._session.flush()
        return item

    async def get(self, item_id: int) -> MeasureQueueItem | None:
        """Look up a single queue item by id."""
        return await self._session.get(MeasureQueueItem, item_id)

    async def increment_attempts(self, item: MeasureQueueItem) -> MeasureQueueItem:
        """Increment a queue item's retry counter by one."""
        item.attempts += 1
        await self._session.flush()
        return item


class AttemptRepository:
    """Repository for the insert-only `attempts` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        queue_id: int,
        proxy_ref: str | None,
        outcome: Outcome,
        duration_ms: int,
        error: str | None = None,
    ) -> Attempt:
        """Insert an attempt record for one (queue item) try."""
        attempt = Attempt(
            queue_id=queue_id,
            proxy_ref=proxy_ref,
            outcome=outcome,
            error=error,
            duration_ms=duration_ms,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def recent_for_proxy_ref(
        self, proxy_ref: str, *, since: datetime.datetime, outcomes: tuple[Outcome, ...]
    ) -> list[Attempt]:
        """Attempts for `proxy_ref` with one of `outcomes`, created at/after `since`."""
        result = await self._session.execute(
            select(Attempt).where(
                Attempt.proxy_ref == proxy_ref,
                Attempt.outcome.in_(outcomes),
                Attempt.created_at >= since,
            )
        )
        return list(result.scalars().all())

    async def for_run(self, run_id: int) -> list[Attempt]:
        """All attempts belonging to queue items of `run_id` (joined via `measure_queue`)."""
        result = await self._session.execute(
            select(Attempt)
            .join(MeasureQueueItem, Attempt.queue_id == MeasureQueueItem.id)
            .where(MeasureQueueItem.run_id == run_id)
        )
        return list(result.scalars().all())
