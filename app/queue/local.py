"""LocalTaskQueue (ADR-0009) — `TaskQueue` over the local flat-file store, no cross-process locking.

Single machine, in-process: unlike `PgTaskQueue`'s `FOR UPDATE SKIP LOCKED`,
there is no lock against concurrent claimers across processes here — that
concurrency guarantee is Postgres-only. Safe for this backend's single-worker-
pool-in-one-process use case (ADR-0009).
"""

import datetime

from app.enums import QueueStatus
from app.queue.base import Pair, QueueItem
from app.storage.local import LocalMeasureQueueRepository


def _to_dto(row: object) -> QueueItem:
    return QueueItem(
        id=row.id,  # type: ignore[attr-defined]
        run_id=row.run_id,  # type: ignore[attr-defined]
        product_id=row.product_id,  # type: ignore[attr-defined]
        region_id=row.region_id,  # type: ignore[attr-defined]
        attempts=row.attempts,  # type: ignore[attr-defined]
    )


class LocalTaskQueue:
    """TaskQueue implementation over `LocalMeasureQueueRepository`."""

    def __init__(self, queue_repo: LocalMeasureQueueRepository) -> None:
        self._queue_repo = queue_repo

    async def enqueue(self, run_id: int, pairs: list[Pair]) -> None:
        """Insert pending queue rows for every pair in this run."""
        for pair in pairs:
            await self._queue_repo.create(run_id=run_id, product_id=pair.product_id, region_id=pair.region_id)

    async def claim(self, limit: int) -> list[QueueItem]:
        """Claim up to `limit` pending items (no cross-process lock — see module docstring)."""
        rows = await self._queue_repo.claim_pending(limit)
        return [_to_dto(row) for row in rows]

    async def complete(self, item: QueueItem, status: QueueStatus) -> None:
        """Mark a claimed item with a terminal status (`DONE`/`FAILED`)."""
        row = await self._queue_repo.get(item.id)
        if row is not None:
            await self._queue_repo.mark(row, status)

    async def reclaim_stale(self, older_than: datetime.timedelta) -> int:
        """Return abandoned `in_progress` items (stale `locked_at`) back to `pending`."""
        threshold = datetime.datetime.now(datetime.UTC) - older_than
        return await self._queue_repo.reclaim_stale(threshold)
