"""Storage seam (ADR-0009) — repository Protocols mirroring `app/repositories.py` exactly.

Two backends implement these Protocols: `app/storage/local.py` (flat files,
default, no DB) and `app/storage/postgres.py` (thin adapter over the existing
SQLAlchemy repositories). `make_storage(settings)` picks one by
`settings.storage_backend`.
"""

from typing import Any, Protocol

from app.collectors.base import PriceObservation
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.models import Attempt, MeasureQueueItem, PriceSnapshot, Product, Region, Run


class ProductRepositoryProto(Protocol):
    """Repository seam for the `products` reference table."""

    async def upsert(
        self, *, marketplace: Marketplace, sku: str, url: str, name: str, is_active: bool = True
    ) -> Product: ...

    async def list_active(self) -> list[Product]: ...

    async def get_by_sku(self, *, marketplace: Marketplace, sku: str) -> Product | None: ...

    async def get_by_id(self, product_id: int) -> Product | None: ...


class RegionRepositoryProto(Protocol):
    """Repository seam for the `regions` reference table."""

    async def upsert(
        self, *, code: str, name: str, geo: dict[str, Any], is_active: bool = True
    ) -> Region: ...

    async def list_active(self) -> list[Region]: ...

    async def get_by_code(self, code: str) -> Region | None: ...

    async def get_by_id(self, region_id: int) -> Region | None: ...


class RunRepositoryProto(Protocol):
    """Repository seam for the `runs` table."""

    async def create(self, *, mode: RunMode) -> Run: ...

    async def get(self, run_id: int) -> Run | None: ...

    async def list_recent(self, limit: int = 10) -> list[Run]: ...

    async def finish(self, run: Run, status: RunStatus, stats: dict[str, Any]) -> Run: ...


class PriceSnapshotRepositoryProto(Protocol):
    """Repository seam for the insert-only `price_snapshots` table."""

    async def add(
        self, *, product_id: int, region_id: int, run_id: int, obs: PriceObservation
    ) -> PriceSnapshot: ...

    async def list_all(self) -> list[PriceSnapshot]: ...


class MeasureQueueRepositoryProto(Protocol):
    """Repository seam for the `measure_queue` table."""

    async def create(self, *, run_id: int, product_id: int, region_id: int) -> MeasureQueueItem: ...

    async def mark(self, item: MeasureQueueItem, status: QueueStatus) -> MeasureQueueItem: ...

    async def get(self, item_id: int) -> MeasureQueueItem | None: ...

    async def increment_attempts(self, item: MeasureQueueItem) -> MeasureQueueItem: ...


class AttemptRepositoryProto(Protocol):
    """Repository seam for the insert-only `attempts` table."""

    async def add(
        self,
        *,
        queue_id: int,
        proxy_ref: str | None,
        outcome: Outcome,
        duration_ms: int,
        error: str | None = None,
    ) -> Attempt: ...

    async def recent_for_proxy_ref(
        self, proxy_ref: str, *, since: Any, outcomes: tuple[Outcome, ...]
    ) -> list[Attempt]: ...

    async def for_run(self, run_id: int) -> list[Attempt]: ...


class Storage(Protocol):
    """A bound set of repositories over one unit-of-work (a session, or the local store)."""

    products: ProductRepositoryProto
    regions: RegionRepositoryProto
    runs: RunRepositoryProto
    snapshots: PriceSnapshotRepositoryProto
    queue_items: MeasureQueueRepositoryProto
    attempts: AttemptRepositoryProto

    async def commit(self) -> None: ...
