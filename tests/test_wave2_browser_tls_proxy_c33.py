from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_browser_tls_proxy_c33.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()
TREE = ast.parse(SOURCE)


class BrowserTlsProxyC33Tests(unittest.TestCase):
    def test_compares_http_and_https_proxy_candidates_for_shorthand(self):
        self.assertIn('["http", "https"]', SOURCE)
        self.assertIn('scheme_in_cached_value', SOURCE)

    def test_requires_https_secure_context(self):
        self.assertIn('protocol == "https:"', SOURCE)
        self.assertIn('secure_context', SOURCE)
        self.assertIn('window.isSecureContext', SOURCE)

    def test_security_details_are_observed_when_available(self):
        self.assertIn('security_details', SOURCE)
        self.assertIn('details.get(\'protocol\')', SOURCE)

    def test_ozon_probe_is_navigation_only(self):
        self.assertIn('OZON_HTTPS = "https://www.ozon.ru/?__rr=1&abt_att=1"', SOURCE)
        self.assertNotIn('entrypoint-api', LOW)
        self.assertNotIn('composer-api', LOW)

    def test_no_captcha_submission_or_pointer_automation(self):
        for forbidden in (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "pointertrajectory",
            "pointer_trajectory",
        ):
            self.assertNotIn(forbidden, LOW)

    def test_no_ignore_https_errors(self):
        self.assertNotIn("ignore_https_errors", LOW)


if __name__ == "__main__":
    unittest.main()
