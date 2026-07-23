"""Unit tests for retry/backoff helpers — pure, no sleeping, always runs in CI."""

from app.enums import Outcome
from app.scheduler.retry import backoff_delay, is_retriable


def test_backoff_delay_is_monotonic_non_decreasing() -> None:
    delays = [backoff_delay(attempt, base=2.0, cap=60.0) for attempt in range(1, 8)]
    assert all(later >= earlier for earlier, later in zip(delays, delays[1:], strict=False))


def test_backoff_delay_capped() -> None:
    assert backoff_delay(20, base=2.0, cap=60.0) == 60.0


def test_backoff_delay_first_attempt_is_base() -> None:
    assert backoff_delay(1, base=2.0, cap=60.0) == 2.0


def test_hard_ban_is_retriable() -> None:
    assert is_retriable(Outcome.HARD_BAN) is True


def test_timeout_is_retriable() -> None:
    assert is_retriable(Outcome.TIMEOUT) is True


def test_ok_is_not_retriable() -> None:
    assert is_retriable(Outcome.OK) is False


def test_soft_ban_is_not_retriable() -> None:
    assert is_retriable(Outcome.SOFT_BAN) is False


def test_error_is_not_retriable() -> None:
    assert is_retriable(Outcome.ERROR) is False
