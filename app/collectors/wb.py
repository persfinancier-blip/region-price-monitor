"""WB collector — direct `requests` connection to `card.wb.ru` (ADR-0005)."""

import requests

from app.collectors.base import PriceObservation
from app.collectors.wb_parse import parse_wb_card
from app.config import get_settings
from app.enums import Marketplace
from app.models import Product, Region

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


class WbCollector:
    """Reads current price/availability for a WB product from the card endpoint."""

    marketplace = Marketplace.WB

    def collect(self, product: Product, region: Region) -> PriceObservation:
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
        )
        if response.status_code != 200 or not response.text.strip():
            raise ValueError(
                f"WB card request failed: HTTP {response.status_code} for nm={product.sku}, dest={dest}"
            )
        return parse_wb_card(response.json())
