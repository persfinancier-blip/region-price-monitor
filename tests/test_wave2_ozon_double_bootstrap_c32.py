from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_double_bootstrap_c32.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()


class OzonDoubleBootstrapC32Tests(unittest.TestCase):
    def test_same_context_is_reused_for_both_browser_launches(self):
        self.assertIn("first = _one_browser_run(Camoufox, context, visible=False", SOURCE)
        self.assertIn("second = _one_browser_run(Camoufox, context, visible=True", SOURCE)
        self.assertEqual(SOURCE.count("context, session_id = _fresh_context"), 1)

    def test_sequence_is_headless_then_visible(self):
        first_pos = SOURCE.index("visible=False")
        second_pos = SOURCE.index("visible=True", first_pos)
        self.assertLess(first_pos, second_pos)

    def test_sticky_ip_is_checked_between_runs(self):
        self.assertIn("after_run1_ip", SOURCE)
        self.assertIn("same_ip != selected_ip", SOURCE)
        self.assertIn("final_ip != selected_ip", SOURCE)

    def test_full_cookie_state_and_ready_cookie_are_observed(self):
        self.assertIn("page.context.cookies()", SOURCE)
        self.assertIn('READY_COOKIE = "__Secure-ext_xcid"', SOURCE)
        self.assertIn("cookie_names", SOURCE)

    def test_browser_native_api_is_used(self):
        self.assertIn("await fetch(url", SOURCE)
        self.assertIn('credentials: "include"', SOURCE)
        self.assertIn("ozon._parse_entrypoint_price", SOURCE)

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
