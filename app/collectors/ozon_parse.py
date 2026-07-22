"""Pure parsing of the Ozon composer-api `page/json/v2` response — no I/O."""

import json
from decimal import Decimal
from typing import Any

from app.collectors.base import PriceObservation


class OzonParseError(ValueError):
    """The composer-api payload has no usable price widget (empty/anti-bot/captcha page)."""


def _find_price_widget(widget_states: dict[str, Any]) -> dict[str, Any] | None:
    for key, value in widget_states.items():
        if "webPrice" not in key and "webSale" not in key:
            continue
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("price"):
            return parsed
    return None


def _is_available(widget_states: dict[str, Any]) -> bool:
    for key in widget_states:
        if "webOutOfStock" in key or "webNotFound" in key:
            return False
    return True


def _to_decimal(value: Any) -> Decimal:
    text = str(value)
    text = "".join(ch for ch in text if ch.isdigit() or ch in ".,")
    return Decimal(text.replace(",", "."))


def parse_ozon(payload: dict[str, Any]) -> PriceObservation:
    """Parse an Ozon composer-api response into a PriceObservation.

    The price fields live inside `widgetStates`, keyed by widget name (e.g.
    `webPrice-...`), with values that are themselves JSON-encoded strings.
    """
    widget_states = payload.get("widgetStates") or {}
    if not widget_states:
        raise OzonParseError("Ozon composer-api response has no widgetStates (empty/anti-bot page)")

    price_widget = _find_price_widget(widget_states)
    if price_widget is None:
        raise OzonParseError("Ozon composer-api response has no price widget (empty/anti-bot page)")

    price = _to_decimal(price_widget["price"])
    price_base_raw = price_widget.get("originalPrice") or price_widget.get("price")
    price_base = _to_decimal(price_base_raw)
    card_price_raw = price_widget.get("cardPrice")
    price_card = _to_decimal(card_price_raw) if card_price_raw else None

    return PriceObservation(
        price=price,
        price_base=price_base,
        price_card=price_card,
        currency="RUB",
        is_available=_is_available(widget_states),
        raw=price_widget,
    )
