"""Unit tests for parse_wb_card — no network, always runs in CI."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.collectors.wb_parse import parse_wb_card

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wb_card_sample.json"


def _load_sample() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_parse_wb_card_price_from_kopecks() -> None:
    obs = parse_wb_card(_load_sample())

    assert obs.price == Decimal("2590.00")
    assert obs.price_base == Decimal("3500.00")


def test_parse_wb_card_price_card_is_none() -> None:
    obs = parse_wb_card(_load_sample())

    assert obs.price_card is None


def test_parse_wb_card_currency_is_rub() -> None:
    obs = parse_wb_card(_load_sample())

    assert obs.currency == "RUB"


def test_parse_wb_card_is_available_true_when_stocked() -> None:
    obs = parse_wb_card(_load_sample())

    assert obs.is_available is True


def test_parse_wb_card_is_available_false_when_all_qty_zero() -> None:
    payload = copy.deepcopy(_load_sample())
    for stock in payload["data"]["products"][0]["sizes"][0]["stocks"]:
        stock["qty"] = 0

    obs = parse_wb_card(payload)

    assert obs.is_available is False


def test_parse_wb_card_raises_on_empty_products() -> None:
    with pytest.raises(ValueError, match="no products"):
        parse_wb_card({"data": {"products": []}})
