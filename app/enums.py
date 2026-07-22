"""String-backed enums shared across ORM models."""

import enum


class Marketplace(enum.StrEnum):
    """Supported marketplaces."""

    WB = "wb"
    OZON = "ozon"


class RunMode(enum.StrEnum):
    """How a run was triggered."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"


class RunStatus(enum.StrEnum):
    """Lifecycle status of a run."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class QueueStatus(enum.StrEnum):
    """Lifecycle status of a measure_queue item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class Outcome(enum.StrEnum):
    """Outcome of a single collection attempt."""

    OK = "ok"
    SOFT_BAN = "soft_ban"
    HARD_BAN = "hard_ban"
    TIMEOUT = "timeout"
    ERROR = "error"
