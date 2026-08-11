from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


class OzonDirectEndpointC17Tests(unittest.TestCase):
    def test_probe_is_zero_cookie_direct_entrypoint(self):
        source = (TOOLS / "probe_ozon_direct_endpoint_c17.py").read_text(encoding="utf-8")
        self.assertIn('"zero_cookie_request": True', source)
        self.assertIn('"no_home_warmup": True', source)
        self.assertIn('"no_product_html_request": True', source)
        self.assertIn('"no_browser": True', source)
        self.assertNotIn("cookies=", source)
        self.assertNotIn('GET", "https://www.ozon.ru/"', source)

    def test_probe_selects_sticky_mobile_session_first(self):
        source = (TOOLS / "probe_ozon_direct_endpoint_c17.py").read_text(encoding="utf-8")
        self.assertIn("find_mobile_proxy", source)
        self.assertIn("rotate_session", source)
        self.assertIn("tries=15", source)

    def test_probe_has_typed_success_and_challenge_gates(self):
        source = (TOOLS / "probe_ozon_direct_endpoint_c17.py").read_text(encoding="utf-8")
        self.assertIn("OZON_DIRECT_ENDPOINT_ZERO_COOKIE_DATA_ACCESS_PROVEN", source)
        self.assertIn("OZON_DIRECT_ENDPOINT_ZERO_COOKIE_CHALLENGED", source)
        self.assertIn("OZON_DIRECT_ENDPOINT_O3_HEADERS_STALE", source)

    def test_probe_has_no_browser_dependencies(self):
        source = (TOOLS / "probe_ozon_direct_endpoint_c17.py").read_text(encoding="utf-8").lower()
        for token in ("playwright", "selenium", "chromium.launch", "sync_playwright("):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
