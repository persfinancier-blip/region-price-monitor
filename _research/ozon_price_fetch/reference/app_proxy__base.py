"""ProxyProvider contract (ADR-0003) — provider-agnostic, no vendor coupling here."""

from dataclasses import dataclass
from typing import Protocol

from app.enums import Outcome

RegionCode = str


@dataclass(frozen=True)
class ProxyLease:
    """A proxy handed out for a single collection attempt."""

    provider: str
    region_code: RegionCode
    proxy_url: str | None
    ref: str


class ProxyProvider(Protocol):
    """Acquire a proxy lease for a region and report back the outcome of using it."""

    async def acquire(self, region_code: RegionCode) -> ProxyLease:
        """Return a proxy lease to use for one attempt in the given region."""
        ...

    async def report(self, lease: ProxyLease, outcome: Outcome) -> None:
        """Feed back the outcome of a completed attempt for health/rotation purposes."""
        ...


def proxy_url_to_requests_dict(proxy_url: str | None) -> dict[str, str] | None:
    """Turn a full proxy URL into a `requests`-compatible proxies dict, or None for direct."""
    if proxy_url is None:
        return None
    return {"http": proxy_url, "https": proxy_url}
