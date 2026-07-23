"""RateLimiter/NullRateLimiter — pure, no real sleeping (clock and sleep are patched)."""

from unittest.mock import patch

from app.collectors.pacing import NullRateLimiter, RateLimiter
from app.enums import Marketplace


async def test_null_rate_limiter_never_delays() -> None:
    limiter = NullRateLimiter()
    with patch("asyncio.sleep") as mock_sleep:
        await limiter.wait(Marketplace.WB)
        await limiter.wait(Marketplace.WB)
    mock_sleep.assert_not_called()


async def test_rate_limiter_first_call_never_delays() -> None:
    limiter = RateLimiter(min_interval_s={Marketplace.WB: 1.0}, jitter_s=0.0)
    with patch("asyncio.sleep") as mock_sleep:
        await limiter.wait(Marketplace.WB)
    mock_sleep.assert_not_called()


async def test_rate_limiter_enforces_min_interval() -> None:
    limiter = RateLimiter(min_interval_s={Marketplace.WB: 1.0}, jitter_s=0.0)

    clock = [0.0]

    def fake_time() -> float:
        return clock[0]

    with (
        patch("asyncio.get_running_loop") as mock_loop,
        patch("asyncio.sleep") as mock_sleep,
    ):
        mock_loop.return_value.time.side_effect = fake_time
        await limiter.wait(Marketplace.WB)
        clock[0] = 0.2  # only 0.2s elapsed, need 1.0s
        await limiter.wait(Marketplace.WB)

    mock_sleep.assert_called_once()
    (delay,) = mock_sleep.call_args.args
    assert delay == 0.8


async def test_rate_limiter_stays_within_jitter_bounds() -> None:
    limiter = RateLimiter(min_interval_s={Marketplace.WB: 1.0}, jitter_s=0.5)

    clock = [0.0]

    def fake_time() -> float:
        return clock[0]

    with (
        patch("asyncio.get_running_loop") as mock_loop,
        patch("asyncio.sleep") as mock_sleep,
        patch("random.uniform", return_value=0.5),
    ):
        mock_loop.return_value.time.side_effect = fake_time
        await limiter.wait(Marketplace.WB)
        clock[0] = 0.0
        await limiter.wait(Marketplace.WB)

    mock_sleep.assert_called_once()
    (delay,) = mock_sleep.call_args.args
    assert 1.0 <= delay <= 1.5


async def test_rate_limiter_per_marketplace_independent() -> None:
    limiter = RateLimiter(min_interval_s={Marketplace.WB: 1.0, Marketplace.OZON: 2.0}, jitter_s=0.0)

    clock = [0.0]

    def fake_time() -> float:
        return clock[0]

    with (
        patch("asyncio.get_running_loop") as mock_loop,
        patch("asyncio.sleep") as mock_sleep,
    ):
        mock_loop.return_value.time.side_effect = fake_time
        await limiter.wait(Marketplace.WB)
        await limiter.wait(Marketplace.OZON)

    mock_sleep.assert_not_called()
