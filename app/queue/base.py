"""TaskQueue contract (ADR-0004) — a Postgres-backed queue seam over `measure_queue`."""

import datetime
from dataclasses import dataclass
from typing import Protocol

from app.enums import QueueStatus


@dataclass(frozen=True)
class Pair:
    """A (product, region) pair to enqueue for measurement within a run."""

    product_id: int
    region_id: int


@dataclass(frozen=True)
class QueueItem:
    """A claimed unit of work from the queue."""

    id: int
    run_id: int
    product_id: int
    region_id: int
    attempts: int


class TaskQueue(Protocol):
    """Queue seam — Postgres today (ADR-0004), a broker is a drop-in later."""

    async def enqueue(self, run_id: int, pairs: list[Pair]) -> None:
        """Insert pending queue rows for every pair in this run."""
        ...

    async def claim(self, limit: int) -> list[QueueItem]:
        """Atomically claim up to `limit` pending items (`FOR UPDATE SKIP LOCKED`)."""
        ...

    async def complete(self, item: QueueItem, status: QueueStatus) -> None:
        """Mark a claimed item with a terminal status (`DONE`/`FAILED`)."""
        ...

    async def reclaim_stale(self, older_than: datetime.timedelta) -> int:
        """Return abandoned `in_progress` items (stale `locked_at`) back to `pending`."""
        ...
