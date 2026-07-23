"""Postgres storage adapter (ADR-0009) — thin `Storage` wrapper over `app/repositories.py`.

No logic change from the pre-seam repositories; this only bundles them behind
the same `Storage` shape the local backend exposes, bound to one `AsyncSession`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import (
    AttemptRepository,
    MeasureQueueRepository,
    PriceSnapshotRepository,
    ProductRepository,
    RegionRepository,
    RunRepository,
)


class PostgresStorage:
    """Bound set of SQLAlchemy repositories over one `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.regions = RegionRepository(session)
        self.runs = RunRepository(session)
        self.snapshots = PriceSnapshotRepository(session)
        self.queue_items = MeasureQueueRepository(session)
        self.attempts = AttemptRepository(session)

    async def commit(self) -> None:
        """Commit the underlying session."""
        await self.session.commit()
