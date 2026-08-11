from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_browser_engine_ab_c35.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()


class OzonBrowserEngineAbC35Tests(unittest.TestCase):
    def test_script_parses(self):
        ast.parse(SOURCE)

    def test_stock_firefox_and_camoufox_are_compared(self):
        self.assertIn("_run_stock_firefox", SOURCE)
        self.assertIn("_run_camoufox", SOURCE)
        self.assertIn("pw.firefox.launch", SOURCE)
        self.assertIn("Camoufox", SOURCE)

    def test_same_context_is_reused(self):
        self.assertIn("stock = _run_stock_firefox(context", SOURCE)
        self.assertIn("camo = _run_camoufox(context", SOURCE)
        self.assertIn("middle_ip != before_ip", SOURCE)
        self.assertIn("after_ip != before_ip", SOURCE)

    def test_stock_firefox_runs_first(self):
        self.assertLess(SOURCE.index("stock = _run_stock_firefox"), SOURCE.index("camo = _run_camoufox"))

    def test_no_stealth_tuning_is_added_to_stock_firefox(self):
        for forbidden in ("stealth", "navigator.webdriver", "add_init_script", "user_agent="):
            self.assertNotIn(forbidden, LOW)

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
