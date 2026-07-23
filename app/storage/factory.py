"""`make_storage(settings)` — Storage-factory seam picking `local` or `postgres` (ADR-0009)."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from app.config import Settings
from app.storage.base import Storage

StorageFactory = Callable[[], AbstractAsyncContextManager[Storage]]


@asynccontextmanager
async def _local_storage_factory(local_state_dir: str) -> AsyncIterator[Storage]:
    from app.storage.local import LocalStorage

    os.makedirs(local_state_dir, exist_ok=True)
    yield LocalStorage(local_state_dir)  # type: ignore[misc]


def make_storage(settings: Settings) -> StorageFactory:
    """Return a `Storage`-yielding async context manager factory for `settings.storage_backend`."""
    if settings.storage_backend == "local":

        def _local() -> AbstractAsyncContextManager[Storage]:
            return _local_storage_factory(settings.local_state_dir)

        return _local

    if settings.storage_backend == "postgres":
        from app.db import get_session
        from app.storage.postgres import PostgresStorage

        @asynccontextmanager
        async def _postgres() -> AsyncIterator[Storage]:
            async with get_session() as session:
                yield PostgresStorage(session)  # type: ignore[misc]

        return _postgres

    raise ValueError(f"unknown storage_backend: {settings.storage_backend!r}")
