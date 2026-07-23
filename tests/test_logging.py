"""JsonFormatter — valid JSON, expected keys, no secret/price leakage."""

import json
import logging
from decimal import Decimal

from app.obs.logging import JsonFormatter


def _make_record(msg: str, extra: dict) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_valid_json_with_expected_keys() -> None:
    formatter = JsonFormatter()
    record = _make_record("measurement", {"run_id": 1, "outcome": "ok", "duration_ms": 120})

    line = formatter.format(record)
    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "measurement"
    assert "timestamp" in payload
    assert payload["run_id"] == 1
    assert payload["outcome"] == "ok"
    assert payload["duration_ms"] == 120


def test_json_formatter_no_price_or_decimal_leak() -> None:
    formatter = JsonFormatter()
    representative_extra = {
        "run_id": 1,
        "marketplace": "wb",
        "product_id": 5,
        "sku": "12345",
        "region_code": "msk",
        "proxy_ref": "static:msk:proxy.example.com",
        "outcome": "ok",
        "duration_ms": 250,
        "error": None,
    }
    record = _make_record("measurement", representative_extra)

    line = formatter.format(record)
    payload = json.loads(line)

    assert "price" not in payload
    assert "price_base" not in payload
    assert "price_card" not in payload
    assert not any(isinstance(v, Decimal) for v in payload.values())


def test_json_formatter_no_raw_proxy_url_leak() -> None:
    formatter = JsonFormatter()
    record = _make_record("measurement", {"proxy_ref": "static:msk:proxy.example.com"})

    line = formatter.format(record)
    payload = json.loads(line)

    assert payload["proxy_ref"] == "static:msk:proxy.example.com"
    assert "@" not in payload["proxy_ref"]
    assert "://" not in payload["proxy_ref"]
