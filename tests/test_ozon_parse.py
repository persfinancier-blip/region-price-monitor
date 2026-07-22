"""Unit tests for parse_ozon — no network, always runs in CI."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.collectors.ozon_parse import OzonParseError, parse_ozon

FIXTURE_PATH = Path(__file__).parent / "data" / "ozon_composer_sample.json"


def _load_sample() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_parse_ozon_price() -> None:
    obs = parse_ozon(_load_sample())

    assert obs.price == Decimal("2590")


def test_parse_ozon_price_base_is_original_price() -> None:
    obs = parse_ozon(_load_sample())

    assert obs.price_base == Decimal("3500")


def test_parse_ozon_price_card() -> None:
    obs = parse_ozon(_load_sample())

    assert obs.price_card == Decimal("2390")


def test_parse_ozon_currency_is_rub() -> None:
    obs = parse_ozon(_load_sample())

    assert obs.currency == "RUB"


def test_parse_ozon_is_available_true_by_default() -> None:
    obs = parse_ozon(_load_sample())

    assert obs.is_available is True


def test_parse_ozon_is_available_false_on_out_of_stock_widget() -> None:
    payload = _load_sample()
    payload["widgetStates"]["webOutOfStock-3129447770-default-1"] = "{}"

    obs = parse_ozon(payload)

    assert obs.is_available is False


def test_parse_ozon_raises_on_empty_widget_states() -> None:
    with pytest.raises(OzonParseError, match="no widgetStates"):
        parse_ozon({"widgetStates": {}})


def test_parse_ozon_raises_on_missing_price_widget() -> None:
    with pytest.raises(OzonParseError, match="no price widget"):
        parse_ozon({"widgetStates": {"webSomethingElse-1": "{}"}})
