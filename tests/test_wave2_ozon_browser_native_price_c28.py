from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_browser_native_price_c28.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()


class OzonBrowserNativePriceC28Tests(unittest.TestCase):
    def test_no_curl_handoff_exists(self):
        self.assertNotIn("curl_cffi", LOW)
        self.assertNotIn("impersonate=", LOW)

    def test_browser_native_fetch_is_used(self):
        self.assertIn("await fetch(url", SOURCE)
        self.assertIn('credentials: "include"', SOURCE)

    def test_same_sticky_ip_is_required(self):
        self.assertIn("browser_ip != selected_ip", SOURCE)
        self.assertIn("_selected_context", SOURCE)

    def test_full_browser_cookie_jar_stays_in_context(self):
        self.assertIn("cookies = list(page.context.cookies())", SOURCE)
        self.assertNotIn("session.cookies", SOURCE)

    def test_strict_price_parser_is_reused(self):
        self.assertIn("ozon._parse_entrypoint_price", SOURCE)
        self.assertIn("ozon._is_challenge", SOURCE)

    def test_no_captcha_submission_or_pointer_automation(self):
        for forbidden in (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "pointertrajectory",
            "pointer_trajectory",
        ):
            self.assertNotIn(forbidden, LOW)


if __name__ == "__main__":
    unittest.main()
