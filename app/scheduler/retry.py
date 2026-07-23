"""Pure retry/backoff helpers — no sleeping, no I/O."""

from app.enums import Outcome

_RETRIABLE_OUTCOMES = {Outcome.HARD_BAN, Outcome.TIMEOUT}


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff delay for the given attempt number (1-indexed), capped at `cap`."""
    return min(base * float(2 ** max(attempt - 1, 0)), cap)


def is_retriable(outcome: Outcome) -> bool:
    """Whether this outcome should be retried (`HARD_BAN`, `TIMEOUT`)."""
    return outcome in _RETRIABLE_OUTCOMES
