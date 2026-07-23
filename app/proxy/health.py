"""Proxy health/cooldown, derived from `attempts` — no new schema (ADR-0007 §4)."""

import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.enums import Outcome
from app.proxy.base import ProxyLease, ProxyProvider, RegionCode

if TYPE_CHECKING:
    from app.config import Settings
    from app.storage.factory import StorageFactory

logger = logging.getLogger(__name__)

_BAN_OUTCOMES = (Outcome.HARD_BAN, Outcome.SOFT_BAN)


@dataclass(frozen=True)
class HealthVerdict:
    """Whether a `proxy_ref` is cooling down, and until when."""

    cooling_down: bool
    until: datetime.datetime | None
    ban_count: int


class ProxyOnCooldown(RuntimeError):
    """Raised by `HealthAwareProxyProvider.acquire` when the region's proxy is cooling down."""

    def __init__(self, region_code: RegionCode, proxy_ref: str, until: datetime.datetime) -> None:
        super().__init__(f"proxy {proxy_ref!r} for region {region_code!r} cooling down until {until}")
        self.region_code = region_code
        self.proxy_ref = proxy_ref
        self.until = until


def evaluate_health(
    ban_count: int,
    last_ban_at: datetime.datetime | None,
    now: datetime.datetime,
    *,
    threshold: int,
    cooldown_s: int,
) -> HealthVerdict:
    """Pure decision: cooling down when `ban_count >= threshold`, until `last_ban_at + cooldown_s`."""
    if ban_count < threshold or last_ban_at is None:
        return HealthVerdict(cooling_down=False, until=None, ban_count=ban_count)
    until = last_ban_at + datetime.timedelta(seconds=cooldown_s)
    return HealthVerdict(cooling_down=now < until, until=until, ban_count=ban_count)


class ProxyHealthService:
    """Reads recent `attempts` for a `proxy_ref` (via the storage seam) and evaluates cooldown."""

    def __init__(self, storage_factory: "StorageFactory", settings: "Settings") -> None:
        self._storage_factory = storage_factory
        self._settings = settings

    async def verdict(self, region_code: RegionCode, proxy_ref: str) -> HealthVerdict:
        """Aggregate recent ban outcomes for `proxy_ref` and evaluate cooldown."""
        now = datetime.datetime.now(datetime.UTC)
        window_start = now - datetime.timedelta(seconds=self._settings.proxy_health_window_s)

        async with self._storage_factory() as storage:
            attempts = await storage.attempts.recent_for_proxy_ref(
                proxy_ref, since=window_start, outcomes=_BAN_OUTCOMES
            )

        ban_count = len(attempts)
        last_ban_at = max((a.created_at for a in attempts), default=None)

        return evaluate_health(
            ban_count,
            last_ban_at,
            now,
            threshold=self._settings.proxy_ban_threshold,
            cooldown_s=self._settings.proxy_cooldown_s,
        )


class HealthAwareProxyProvider:
    """Decorates a base `ProxyProvider` with cooldown checks (ADR-0003 seam preserved)."""

    def __init__(self, base: ProxyProvider, health: ProxyHealthService, settings: "Settings") -> None:
        self._base = base
        self._health = health
        self._settings = settings

    async def acquire(self, region_code: RegionCode) -> ProxyLease:
        """Return the base lease, or raise `ProxyOnCooldown` if its proxy is cooling down."""
        lease = await self._base.acquire(region_code)
        try:
            verdict = await self._health.verdict(region_code, lease.ref)
        except Exception:  # noqa: BLE001 — best-effort side-channel: fail open, never block a run
            logger.exception("proxy health check failed, failing open", extra={"region_code": region_code})
            return lease

        if verdict.cooling_down and verdict.until is not None:
            logger.info(
                "proxy.health",
                extra={
                    "region_code": region_code,
                    "proxy_ref": lease.ref,
                    "cooling_down": True,
                    "ban_count": verdict.ban_count,
                    "until": verdict.until,
                },
            )
            raise ProxyOnCooldown(region_code, lease.ref, verdict.until)
        return lease

    async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
        """Delegate to the base provider and emit a `proxy.health` observation event."""
        await self._base.report(lease, outcome)
        logger.info(
            "proxy.health",
            extra={
                "region_code": lease.region_code,
                "proxy_ref": lease.ref,
                "cooling_down": False,
                "outcome": outcome.value,
            },
        )
