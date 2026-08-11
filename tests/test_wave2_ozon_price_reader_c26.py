from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import ozon


class OzonPriceReaderC26Tests(unittest.TestCase):
    def test_entrypoint_exact_price(self):
        payload = {
            "pageInfo": {"url": "/product/3129447770/"},
            "widgetStates": {
                "price-1": '{"price":"1 234 ₽","cardPrice":"1 111 ₽","originalPrice":"1 499 ₽","isAvailable":true}'
            },
            "layout": [{"component": "webPrice", "stateId": "price-1"}],
        }
        result = ozon._parse_entrypoint_price(payload, "3129447770")
        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 1234.0)
        self.assertEqual(result["price_card"], 1111.0)

    def test_challenge_has_no_price(self):
        payload = {"captchaURL": "https://example.test/captcha", "incidentId": "x"}
        self.assertTrue(ozon._is_challenge(payload))
        parsed = ozon._parse_entrypoint_price(payload, "3129447770")
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["error"], "challenge")
        self.assertNotIn("price", parsed)

    def test_no_implicit_legacy_fallback(self):
        with patch.object(ozon, "fetch_price_proxy_first", return_value={"status": "challenge", "path": "sg04_proxy_first"}):
            with patch.object(ozon, "fetch_price_legacy_authenticated") as legacy:
                result = ozon.read_price("1", object(), allow_legacy_fallback=False)
        self.assertEqual(result["status"], "challenge")
        legacy.assert_not_called()

    def test_explicit_legacy_fallback(self):
        with patch.object(ozon, "fetch_price_proxy_first", return_value={"status": "challenge", "path": "sg04_proxy_first"}):
            with patch.object(
                ozon,
                "fetch_price_legacy_authenticated",
                return_value={"status": "price", "price": 999.0, "path": "sg05_authenticated_legacy"},
            ) as legacy:
                result = ozon.read_price(
                    "1",
                    object(),
                    allow_legacy_fallback=True,
                    legacy_cookies=[{"name": "session", "value": "secret"}],
                )
        self.assertEqual(result["status"], "price")
        self.assertTrue(result["fallback_explicit"])
        self.assertEqual(result["primary_status"], "challenge")
        legacy.assert_called_once()

    def test_legacy_proxy_is_optional_and_source_has_no_bypass(self):
        source = (CORE / "ozon.py").read_text(encoding="utf-8").lower()
        self.assertIn("def fetch_price_legacy_authenticated(sku, cookies_list, proxy=none", source)
        self.assertIn("allow_legacy_fallback: bool = false", source)
        for forbidden in (
            "/abt/captcha/result",
            "pointertrajectory",
            "pointer_trajectory",
            "drag_and_drop",
            "actionchains",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
