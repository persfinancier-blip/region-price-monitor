"""Collector contract shared by all marketplace collectors."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.enums import Marketplace
from app.models import Product, Region


@dataclass(frozen=True)
class PriceObservation:
    """A single parsed price/availability reading for a (product, region) pair."""

    price: Decimal
    price_base: Decimal
    price_card: Decimal | None
    currency: str
    is_available: bool
    raw: dict[str, Any] = field(default_factory=dict)


class MarketplaceCollector(Protocol):
    """Contract for a per-marketplace price collector."""

    marketplace: Marketplace

    def collect(self, product: Product, region: Region, proxy_url: str | None = None) -> PriceObservation:
        """Fetch and parse the current price/availability for a product in a region.

        `proxy_url` is a full `http://user:pass@host:port` URL to route the request
        through, or None for a direct connection.
        """
        ...
