from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from probe_ozon_single_run_c23 import _challenge_url, _selected_context


class OzonSingleRunC23Tests(unittest.TestCase):
    def test_challenge_url_accepts_nonempty_string(self):
        self.assertEqual(
            _challenge_url({"captchaURL": " https://example.test/captcha?x=1 "}),
            "https://example.test/captcha?x=1",
        )

    def test_challenge_url_rejects_missing_or_nonstring(self):
        self.assertIsNone(_challenge_url(None))
        self.assertIsNone(_challenge_url({}))
        self.assertIsNone(_challenge_url({"captchaURL": "   "}))
        self.assertIsNone(_challenge_url({"captchaURL": 123}))

    def test_selected_context_reuses_current_run_session(self):
        selected = {
            "session_id": "abc123",
            "identity": {"query": "203.0.113.7"},
            "operator": "MTS",
        }
        context, sid, ip = _selected_context(
            "https://proxy.example:443",
            "user-hold-query",
            "secret",
            selected,
        )
        self.assertEqual(sid, "abc123")
        self.assertEqual(ip, "203.0.113.7")
        self.assertTrue(context.proxy_user.endswith("-hold-session-session-abc123"))
        self.assertEqual(context.proxy_password, "secret")

    def test_runtime_source_has_no_historical_report_dependency_or_submission(self):
        source_path = ROOT / "tools" / "probe_ozon_single_run_c23.py"
        source = source_path.read_text(encoding="utf-8").lower()
        forbidden = (
            "ozon_mobile_proxy_selector_report.json",
            "ozon_same_sticky_direct_c19_report.json",
            "ozon_same_sticky_direct_c19/",
            "/abt/captcha/result",
            "pointertrajectory",
            "pointer_trajectory",
            "selenium",
            "playwright",
            "2captcha",
            "nopecha",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_safe_report_contract_flags_are_present(self):
        source = (ROOT / "tools" / "probe_ozon_single_run_c23.py").read_text(encoding="utf-8")
        self.assertIn('"challenge_submitted": False', source)
        self.assertIn('"credentials_persisted": False', source)
        self.assertIn('"full_urls_persisted": False', source)
        self.assertIn("OZON_SINGLE_RUN_CHALLENGE_IMAGES_SOLVED_LOCAL", source)


if __name__ == "__main__":
    unittest.main()
