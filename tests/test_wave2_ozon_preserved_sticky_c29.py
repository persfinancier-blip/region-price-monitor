from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_preserved_sticky_c29.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()


class OzonPreservedStickyC29Tests(unittest.TestCase):
    def test_existing_sticky_session_is_required(self):
        self.assertIn("hold-session-session-<id>", SOURCE)
        self.assertIn("SESSION_RE", SOURCE)

    def test_no_rotation_selector_is_used(self):
        self.assertNotIn("find_mobile_proxy", SOURCE)
        self.assertNotIn("rotate_session", SOURCE)
        self.assertIn("C29 never rotates", SOURCE)

    def test_cached_local_proxy_is_used(self):
        self.assertIn('LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"', SOURCE)

    def test_exact_same_ip_is_required_in_browser(self):
        self.assertIn("browser_ip != selected_ip", SOURCE)

    def test_browser_native_fetch_keeps_context(self):
        self.assertIn("await fetch(url", SOURCE)
        self.assertIn('credentials: "include"', SOURCE)
        self.assertIn("cookies = list(page.context.cookies())", SOURCE)

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
