from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_exact_bootstrap_c31.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()
TREE = ast.parse(SOURCE)


class OzonExactBootstrapC31Tests(unittest.TestCase):
    def test_exact_expect_request_sequence_is_present(self):
        self.assertIn('page.expect_request("**/api/*-api.bx/page/json/v2**", timeout=30000)', SOURCE)
        self.assertIn('page.goto(HOME_URL, timeout=60000)', SOURCE)
        self.assertIn('page.wait_for_timeout(5000)', SOURCE)
        self.assertIn('page.wait_for_timeout(2500)', SOURCE)

    def test_ozon_is_first_browser_navigation_in_attempt(self):
        bootstrap = SOURCE[SOURCE.index("def _bootstrap_exact"):SOURCE.index("def main")]
        self.assertNotIn("NEUTRAL_URL", bootstrap)
        self.assertIn("page.goto(HOME_URL", bootstrap)

    def test_browser_ip_check_is_after_api_probe(self):
        main = SOURCE[SOURCE.index("def main"):]
        self.assertLess(main.index("api = _probe_api"), main.index("post_ip = _browser_ip"))

    def test_full_cookie_jar_and_ready_cookie_are_observed(self):
        self.assertIn("cookies = list(page.context.cookies())", SOURCE)
        self.assertIn('READY_COOKIE = "__Secure-ext_xcid"', SOURCE)

    def test_browser_native_fetch_uses_product_referrer(self):
        self.assertIn("await fetch(url", SOURCE)
        self.assertIn("productReferrer", SOURCE)
        self.assertIn('credentials: "include"', SOURCE)

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
