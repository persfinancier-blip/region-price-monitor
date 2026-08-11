from __future__ import annotations

from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "probe_ozon_security_ui_c34.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
LOW = SOURCE.lower()


class OzonSecurityUiC34Tests(unittest.TestCase):
    def test_https_proxy_scheme_is_fixed_from_c33(self):
        self.assertIn('"server": f"https://{host}:{port}"', SOURCE)
        self.assertIn("C33-proven HTTPS proxy only", SOURCE)

    def test_main_tls_and_secure_context_are_checked(self):
        self.assertIn("window.isSecureContext", SOURCE)
        self.assertIn("security_details", SOURCE)
        self.assertIn('subject.endswith("ozon.ru")', SOURCE)

    def test_http_mixed_content_is_observed(self):
        self.assertIn('url.lower().startswith("http://")', SOURCE)
        self.assertIn("performance.getEntriesByType('resource')", SOURCE)
        self.assertIn("dom_http_attributes", SOURCE)

    def test_console_security_warnings_are_observed(self):
        self.assertIn('"mixed content" in low', SOURCE)
        self.assertIn('"insecure" in low', SOURCE)

    def test_no_captcha_submission_or_price_fetch(self):
        for forbidden in (
            "/abt/captcha/result",
            "drag_and_drop",
            "actionchains",
            "entrypoint-api",
            "composer-api",
        ):
            self.assertNotIn(forbidden, LOW)

    def test_script_parses(self):
        ast.parse(SOURCE)


if __name__ == "__main__":
    unittest.main()
