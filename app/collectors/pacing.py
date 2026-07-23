"""Anti-bot request pacing — per-marketplace minimum interval + jitter, shared across workers."""

import asyncio
import random
from typing import TYPE_CHECKING, Protocol

from app.enums import Marketplace

if TYPE_CHECKING:
    from app.config import Settings


class RatePacer(Protocol):
    """Waits as needed before the next outbound request for a marketplace."""

    async def wait(self, marketplace: Marketplace) -> None: ...


class NullRateLimiter:
    """No-op pacer — the default for CLI `measure-*` paths and tests."""

    async def wait(self, marketplace: Marketplace) -> None:
        """Return immediately; no pacing applied."""
        return


class RateLimiter:
    """Enforces a per-marketplace minimum interval plus random jitter between requests."""

    def __init__(self, min_interval_s: dict[Marketplace, float], jitter_s: float) -> None:
        self._min_interval_s = min_interval_s
        self._jitter_s = jitter_s
        self._lock = asyncio.Lock()
        self._last_request: dict[Marketplace, float] = {}

    async def wait(self, marketplace: Marketplace) -> None:
        """Sleep, if needed, to honour the minimum interval plus jitter since the last request."""
        min_interval = self._min_interval_s.get(marketplace, 0.0)
        async with self._lock:
            now = asyncio.get_running_loop().time()
            last = self._last_request.get(marketplace)
            delay = 0.0
            if last is not None:
                elapsed = now - last
                target = min_interval + random.uniform(0, self._jitter_s)
                delay = max(0.0, target - elapsed)
            self._last_request[marketplace] = now + delay
        if delay > 0:
            await asyncio.sleep(delay)


def make_rate_limiter(settings: "Settings") -> RateLimiter:
    """Build the real `RateLimiter` from per-marketplace interval settings."""
    return RateLimiter(
        min_interval_s={
            Marketplace.WB: settings.wb_min_interval_s,
            Marketplace.OZON: settings.ozon_min_interval_s,
        },
        jitter_s=settings.request_jitter_s,
    )
