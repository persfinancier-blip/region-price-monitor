from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import probe_ozon_challenge_c20 as c20


class OzonChallengeC20Tests(unittest.TestCase):
    def test_safe_url_meta_never_persists_full_url_or_query(self):
        secret = "https://captcha.example.test/path/session/opaque.png?token=VERY_SECRET&sig=ABC"
        meta = c20._safe_url_meta(secret)
        self.assertEqual(meta["host"], "captcha.example.test")
        rendered = repr(meta)
        self.assertNotIn("VERY_SECRET", rendered)
        self.assertNotIn("sig=ABC", rendered)
        self.assertNotIn("session/opaque", rendered)
        self.assertFalse(meta["full_url_persisted"])
        self.assertTrue(meta["query_present"])

    def test_generic_slider_fingerprint_is_local_classification_only(self):
        result = c20._fingerprint("Move the slider to complete the puzzle")
        self.assertIn("SLIDER_PUZZLE_GENERIC", result)

    def test_probe_source_has_no_external_solver_or_browser_runtime(self):
        source = (TOOLS / "probe_ozon_challenge_c20.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "2captcha",
            "nopecha",
            "solvecaptcha",
            "nocaptcha",
            "playwright",
            "selenium",
            "undetected_chromedriver",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_report_contract_marks_sensitive_material_not_persisted(self):
        source = (TOOLS / "probe_ozon_challenge_c20.py").read_text(encoding="utf-8")
        self.assertIn('"credentials_persisted": False', source)
        self.assertIn('"full_challenge_urls_persisted": False', source)
        self.assertIn('"external_solver_service_used": False', source)


if __name__ == "__main__":
    unittest.main()
