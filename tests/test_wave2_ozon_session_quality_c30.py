from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_session_quality_c30.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()
TREE = ast.parse(SOURCE)


class OzonSessionQualityC30Tests(unittest.TestCase):
    def test_fresh_sticky_is_created_per_attempt(self):
        self.assertIn("rotate_session(proxy_user)", SOURCE)
        self.assertIn("for index in range(1, args.attempts + 1)", SOURCE)

    def test_sticky_is_preserved_inside_attempt(self):
        self.assertIn("browser_ip != selected_ip", SOURCE)
        self.assertIn('"username": context.proxy_user', SOURCE)

    def test_ready_cookie_is_observed(self):
        self.assertIn('READY_COOKIE = "__Secure-ext_xcid"', SOURCE)
        self.assertIn("ready_cookie = READY_COOKIE in names", SOURCE)

    def test_browser_native_api_is_used(self):
        self.assertIn("await fetch(url", SOURCE)
        self.assertIn('credentials: "include"', SOURCE)

    def test_cookie_values_are_not_persisted(self):
        self.assertNotIn("write_text(json.dumps(cookies", SOURCE)
        self.assertNotIn("json.dump(cookies", SOURCE)

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
