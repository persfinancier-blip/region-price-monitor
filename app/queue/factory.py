"""`make_task_queue(settings, storage)` — picks the queue impl by `settings.storage_backend`."""

from typing import cast

from app.config import Settings
from app.queue.base import TaskQueue
from app.storage.base import Storage


def make_task_queue(settings: Settings, storage: Storage) -> TaskQueue:
    """Return a `TaskQueue` bound to `storage`, matching `settings.storage_backend`."""
    if settings.storage_backend == "local":
        from app.queue.local import LocalTaskQueue
        from app.storage.local import LocalMeasureQueueRepository

        return LocalTaskQueue(cast(LocalMeasureQueueRepository, storage.queue_items))

    from app.queue.postgres import PgTaskQueue
    from app.storage.postgres import PostgresStorage

    return PgTaskQueue(cast(PostgresStorage, storage).session)
