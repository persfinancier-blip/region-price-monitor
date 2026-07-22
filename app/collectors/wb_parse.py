"""Pure parsing of the WB `card.wb.ru` v2 response — no I/O."""

from decimal import Decimal
from typing import Any

from app.collectors.base import PriceObservation


def parse_wb_card(payload: dict[str, Any]) -> PriceObservation:
    """Parse a `card.wb.ru/cards/v2/detail` response into a PriceObservation.

    price_card is None this phase: the WB-wallet price is computed client-side
    and is not present on this endpoint.
    """
    data = payload.get("data", payload)
    products = data.get("products") or []
    if not products:
        raise ValueError("WB card response has no products (empty/blocked response)")

    product = products[0]
    sizes = product.get("sizes") or []
    price_obj = next((size["price"] for size in sizes if size.get("price")), None)
    if price_obj is None:
        raise ValueError("WB card response has no price object (empty/blocked response)")

    price_base = Decimal(str(price_obj["basic"])) / 100
    price = Decimal(str(price_obj["product"])) / 100

    is_available = any(stock.get("qty", 0) > 0 for size in sizes for stock in (size.get("stocks") or []))

    return PriceObservation(
        price=price,
        price_base=price_base,
        price_card=None,
        currency="RUB",
        is_available=is_available,
        raw=product,
    )
