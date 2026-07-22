"""CookieStore contract — a warmed browser session per (marketplace × region) (ADR-0005)."""

import datetime
from dataclasses import dataclass
from typing import Any, Protocol

from app.enums import Marketplace


@dataclass(frozen=True)
class CookieBundle:
    """A warmed Playwright `storage_state` for one (marketplace, region) pair.

    The full warmed cookie set is stored — isolating which single cookie carries
    the region is an open question (ADR-0005), not solved this phase.
    """

    marketplace: Marketplace
    region_code: str
    storage_state: dict[str, Any]
    warmed_at: datetime.datetime
    stale: bool = False
    source_ref: str | None = None


class CookieStore(Protocol):
    """Persists and retrieves warmed cookie bundles, keyed by (marketplace, region_code)."""

    def load(self, marketplace: Marketplace, region_code: str) -> CookieBundle | None:
        """Return the stored bundle for this (marketplace, region), or None if absent."""
        ...

    def save(self, bundle: CookieBundle) -> None:
        """Persist a freshly warmed bundle, replacing any prior one for its key."""
        ...

    def mark_stale(self, marketplace: Marketplace, region_code: str) -> None:
        """Flag the stored bundle for this key as stale (e.g. after a 403/anti-bot outcome)."""
        ...


def is_stale(bundle: CookieBundle, ttl_hours: int) -> bool:
    """A bundle is stale once its TTL has expired or it was explicitly marked stale."""
    if bundle.stale:
        return True
    age_limit = bundle.warmed_at + datetime.timedelta(hours=ttl_hours)
    return age_limit < datetime.datetime.now(datetime.UTC)
