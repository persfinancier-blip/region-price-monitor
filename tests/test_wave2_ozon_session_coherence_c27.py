from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_session_coherence_c27.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")


class OzonSessionCoherenceC27Tests(unittest.TestCase):
    def test_full_cookie_jar_is_not_flattened(self):
        self.assertIn('cookies = list(page.context.cookies())', SOURCE)
        self.assertIn('session.cookies.set(name, value, **kwargs)', SOURCE)
        self.assertNotIn('{c["name"]: c["value"] for c in page.context.cookies()}', SOURCE)

    def test_firefox_browser_uses_firefox_curl_target(self):
        self.assertIn('"firefox": "firefox"', SOURCE)
        self.assertNotIn('IMPERSONATE = ("chrome"', SOURCE)

    def test_same_sticky_ip_is_required_for_browser_and_curl(self):
        self.assertIn('browser["browser_ip"] != selected_ip', SOURCE)
        self.assertIn('curl_ip != selected_ip or curl_ip != browser["browser_ip"]', SOURCE)

    def test_cookie_values_are_not_persisted(self):
        self.assertIn('Cookie values are memory-only', SOURCE)
        self.assertNotIn('write_text(json.dumps(browser["cookies"]', SOURCE)
        self.assertNotIn('json.dump(browser["cookies"]', SOURCE)

    def test_no_captcha_submission_or_pointer_automation(self):
        low = SOURCE.lower()
        for forbidden in (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "pointertrajectory",
            "pointer_trajectory",
        ):
            self.assertNotIn(forbidden, low)


if __name__ == "__main__":
    unittest.main()
