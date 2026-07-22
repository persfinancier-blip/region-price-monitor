"""WB collector — direct `requests` connection to `card.wb.ru` (ADR-0005)."""

import requests

from app.collectors.base import PriceObservation
from app.collectors.wb_parse import parse_wb_card
from app.config import get_settings
from app.enums import Marketplace
from app.models import Product, Region
from app.proxy.base import proxy_url_to_requests_dict

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "ru-RU",
    "Accept-Encoding": "gzip, deflate",  # no brotli — requests won't decode it
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


class WbCollectionError(ValueError):
    """A WB collection attempt failed; carries enough context to classify the Outcome."""

    def __init__(self, message: str, *, status_code: int | None = None, empty_products: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.empty_products = empty_products


class WbCollector:
    """Reads current price/availability for a WB product from the card endpoint."""

    marketplace = Marketplace.WB

    def collect(self, product: Product, region: Region, proxy_url: str | None = None) -> PriceObservation:
        settings = get_settings()
        dest = region.geo["wb"]["dest"]
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": dest,
            "spp": 30,
            "nm": product.sku,
        }
        response = requests.get(
            settings.wb_card_url,
            params=params,
            headers=_HEADERS,
            timeout=settings.http_timeout_s,
            proxies=proxy_url_to_requests_dict(proxy_url),
        )
        if response.status_code != 200 or not response.text.strip():
            raise WbCollectionError(
                f"WB card request failed: HTTP {response.status_code} for nm={product.sku}, dest={dest}",
                status_code=response.status_code,
            )
        try:
            return parse_wb_card(response.json())
        except ValueError as exc:
            raise WbCollectionError(
                f"WB card parse failed for nm={product.sku}, dest={dest}: {exc}",
                status_code=response.status_code,
                empty_products=True,
            ) from exc
