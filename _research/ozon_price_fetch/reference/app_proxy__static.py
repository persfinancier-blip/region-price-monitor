"""StaticProxyProvider — config-driven proxy map, no external calls (ADR-0003)."""

import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.enums import Outcome
from app.proxy.base import ProxyLease, ProxyProvider, RegionCode

if TYPE_CHECKING:
    from app.config import Settings
    from app.storage.factory import StorageFactory

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "static"


def _mask_ref(region_code: RegionCode, proxy_url: str | None) -> str:
    """Build a non-secret attempts.proxy_ref label — host only, never credentials."""
    if proxy_url is None:
        return f"{_PROVIDER_NAME}:{region_code}:direct"
    host = urlsplit(proxy_url).hostname or "unknown"
    return f"{_PROVIDER_NAME}:{region_code}:{host}"


def parse_proxy_map(proxy_map_json: str | None) -> dict[str, str]:
    """Parse the `proxy_map_json` config value into a {region_code: proxy_url} dict."""
    if not proxy_map_json:
        return {}
    try:
        parsed = json.loads(proxy_map_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid proxy_map_json: {exc}") from exc
    if not isinstance(parsed, dict) or not all(isinstance(v, str) for v in parsed.values()):
        raise ValueError("proxy_map_json must be a JSON object of {region_code: proxy_url}")
    return parsed


class StaticProxyProvider:
    """Resolves a region to a proxy URL from a static config map; no rotation/health yet."""

    def __init__(self, proxy_map: dict[str, str], fallback_proxy_url: str | None = None) -> None:
        self._proxy_map = proxy_map
        self._fallback_proxy_url = fallback_proxy_url

    async def acquire(self, region_code: RegionCode) -> ProxyLease:
        """Return the configured proxy for the region, the global fallback, or direct."""
        proxy_url = self._proxy_map.get(region_code, self._fallback_proxy_url)
        return ProxyLease(
            provider=_PROVIDER_NAME,
            region_code=region_code,
            proxy_url=proxy_url,
            ref=_mask_ref(region_code, proxy_url),
        )

    async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
        """No-op this phase — health/rotation strategy lands in Фаза 6."""
        logger.debug("proxy report: region=%s outcome=%s ref=%s", lease.region_code, outcome, lease.ref)


def make_proxy_provider(
    settings: "Settings",
    *,
    storage_factory: "StorageFactory | None" = None,
) -> ProxyProvider:
    """Factory: pick a ProxyProvider implementation by `settings.proxy_provider`.

    Wraps the base provider with `HealthAwareProxyProvider` when
    `settings.proxy_health_enabled` and a `storage_factory` is supplied (Фаза 6.2);
    without a factory (pure CLI `measure-*`), behaviour is unchanged.
    """
    if settings.proxy_provider != "static":
        raise ValueError(f"unknown proxy_provider: {settings.proxy_provider!r}")

    proxy_map = parse_proxy_map(settings.proxy_map_json)
    base: ProxyProvider = StaticProxyProvider(proxy_map, settings.proxy_url)

    if settings.proxy_health_enabled and storage_factory is not None:
        from app.proxy.health import HealthAwareProxyProvider, ProxyHealthService

        health = ProxyHealthService(storage_factory, settings)
        return HealthAwareProxyProvider(base, health, settings)
    return base
