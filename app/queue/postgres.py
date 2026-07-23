"""PgTaskQueue — `measure_queue`-backed TaskQueue using `FOR UPDATE SKIP LOCKED`."""

import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import QueueStatus
from app.models import MeasureQueueItem
from app.queue.base import Pair, QueueItem, TaskQueue


def _to_dto(row: MeasureQueueItem) -> QueueItem:
    return QueueItem(
        id=row.id,
        run_id=row.run_id,
        product_id=row.product_id,
        region_id=row.region_id,
        attempts=row.attempts,
    )


class PgTaskQueue:
    """TaskQueue implementation over the `measure_queue` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, run_id: int, pairs: list[Pair]) -> None:
        """Bulk-insert pending queue rows for this run."""
        self._session.add_all(
            [
                MeasureQueueItem(
                    run_id=run_id,
                    product_id=pair.product_id,
                    region_id=pair.region_id,
                    status=QueueStatus.PENDING,
                )
                for pair in pairs
            ]
        )
        await self._session.flush()

    async def claim(self, limit: int) -> list[QueueItem]:
        """Claim up to `limit` pending rows, locking them against other claimers."""
        result = await self._session.execute(
            select(MeasureQueueItem)
            .where(MeasureQueueItem.status == QueueStatus.PENDING)
            .order_by(MeasureQueueItem.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        if not rows:
            return []
        for row in rows:
            row.status = QueueStatus.IN_PROGRESS
            row.locked_at = datetime.datetime.now(datetime.UTC)
        await self._session.flush()
        return [_to_dto(row) for row in rows]

    async def complete(self, item: QueueItem, status: QueueStatus) -> None:
        """Set the terminal status for a claimed item."""
        await self._session.execute(
            update(MeasureQueueItem).where(MeasureQueueItem.id == item.id).values(status=status)
        )
        await self._session.flush()

    async def reclaim_stale(self, older_than: datetime.timedelta) -> int:
        """Return `in_progress` items whose lock is older than `older_than` to `pending`."""
        threshold = datetime.datetime.now(datetime.UTC) - older_than
        result = await self._session.execute(
            update(MeasureQueueItem)
            .where(MeasureQueueItem.status == QueueStatus.IN_PROGRESS, MeasureQueueItem.locked_at < threshold)
            .values(status=QueueStatus.PENDING, locked_at=None)
        )
        await self._session.flush()
        return int(cast(CursorResult[Any], result).rowcount or 0)


def make_task_queue(session: AsyncSession) -> TaskQueue:
    """Factory: only a Postgres-backed queue this phase."""
    return PgTaskQueue(session)
