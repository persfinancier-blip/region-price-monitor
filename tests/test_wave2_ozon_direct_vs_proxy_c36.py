from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_direct_vs_proxy_c36.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
LOW = SOURCE.lower()


class OzonDirectVsProxyC36Tests(unittest.TestCase):
    def test_script_parses(self):
        self.assertIsInstance(TREE, ast.Module)

    def test_stock_firefox_is_used_for_both_arms(self):
        self.assertIn("pw.firefox.launch(headless=not args.visible)", SOURCE)
        self.assertIn("pw.firefox.launch(headless=not args.visible, proxy=_proxy_dict(proxy_context))", SOURCE)

    def test_direct_and_proxy_arms_are_observed(self):
        self.assertIn('_observe_ozon(direct_browser, "direct")', SOURCE)
        self.assertIn('_observe_ozon(proxied_browser, "mobile_proxy")', SOURCE)

    def test_session_bootstrap_signals_are_observed(self):
        self.assertIn('READY_COOKIE = "__Secure-ext_xcid"', SOURCE)
        self.assertIn('"cookie_names": names', SOURCE)
        self.assertIn('"challenge": challenge', SOURCE)
        self.assertIn('"secure_context":', SOURCE)
        self.assertIn('"egress_ip"', SOURCE)

    def test_no_browser_fingerprint_mutation(self):
        # Check actual code structure instead of matching diagnostic print text such as
        # "user_agent=...".  No browser/context call may receive a user_agent kwarg.
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call):
                keyword_names = {kw.arg for kw in node.keywords if kw.arg is not None}
                self.assertNotIn("user_agent", keyword_names)
        for forbidden in (
            "add_init_script",
            "navigator.webdriver",
            "firefox_user_prefs",
        ):
            self.assertNotIn(forbidden, LOW)

    def test_no_captcha_submission_or_pointer_automation(self):
        forbidden = (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "pointertrajectory",
            "pointer_trajectory",
        )
        for marker in forbidden:
            self.assertNotIn(marker, LOW)


if __name__ == "__main__":
    unittest.main()
