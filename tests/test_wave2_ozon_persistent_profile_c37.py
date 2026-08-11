from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_persistent_profile_c37.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
LOW = SOURCE.lower()


class OzonPersistentProfileC37Tests(unittest.TestCase):
    def test_script_parses(self):
        self.assertIsInstance(TREE, ast.Module)

    def test_persistent_firefox_context_is_used(self):
        self.assertIn("pw.firefox.launch_persistent_context", SOURCE)
        self.assertIn("user_data_dir=str(profile_dir)", SOURCE)

    def test_same_profile_and_sticky_are_reused(self):
        self.assertIn("profile_dir = PROFILE_ROOT / session_id", SOURCE)
        self.assertIn("current_ip != selected_ip", SOURCE)
        self.assertIn("proxy=_proxy_dict(proxy_context)", SOURCE)

    def test_full_cookie_state_and_ready_cookie_are_observed(self):
        self.assertIn("cookies = list(context.cookies())", SOURCE)
        self.assertIn('READY_COOKIE = "__Secure-ext_xcid"', SOURCE)
        self.assertIn('"cookie_names": names', SOURCE)

    def test_no_browser_fingerprint_mutation(self):
        forbidden_call_keywords = {"user_agent", "firefox_user_prefs", "ignore_default_args"}
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in forbidden_call_keywords:
                        self.fail(f"forbidden browser mutation keyword: {kw.arg}")
        self.assertNotIn("navigator.webdriver", LOW)
        self.assertNotIn("add_init_script", LOW)

    def test_no_captcha_submission_or_pointer_automation(self):
        for marker in (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "pointertrajectory",
            "pointer_trajectory",
        ):
            self.assertNotIn(marker, LOW)


if __name__ == "__main__":
    unittest.main()
