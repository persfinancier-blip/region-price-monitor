from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import mobile_proxy


class ClaudeMobileProxyC18Tests(unittest.TestCase):
    def test_rotate_session_from_bare_login(self):
        user, sid = mobile_proxy.rotate_session("abc-mobile-country-RU", "deadbeef")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-deadbeef")
        self.assertEqual(sid, "deadbeef")

    def test_rotate_session_from_hold_query(self):
        user, _ = mobile_proxy.rotate_session("abc-mobile-country-RU-hold-query", "abc123")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-abc123")

    def test_rotate_session_from_hold_query_with_old_id(self):
        user, _ = mobile_proxy.rotate_session("abc-mobile-country-RU-hold-query-old123", "abc123")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-abc123")

    def test_rotate_session_replaces_existing_bound_session(self):
        user, _ = mobile_proxy.rotate_session(
            "abc-mobile-country-RU-hold-session-session-old123", "new456"
        )
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-new456")
        self.assertNotIn("old123", user)

    def test_operator_detection(self):
        samples = [
            ({"isp": "MTS PJSC"}, "MTS"),
            ({"org": "PJSC VimpelCom"}, "BEELINE"),
            ({"asName": "MegaFon"}, "MEGAFON"),
            ({"carrier": "T2 Mobile"}, "TELE2_T2"),
            ({"network": "Scartel Ltd"}, "YOTA"),
        ]
        for payload, expected in samples:
            with self.subTest(payload=payload):
                operator, evidence = mobile_proxy._operator_evidence(payload)
                self.assertEqual(operator, expected)
                self.assertTrue(evidence)

    def test_407_is_typed_as_proxy_auth_failure(self):
        self.assertTrue(
            mobile_proxy._transport_auth_failed(
                {"status_code": 407, "message": "Proxy Authentication Required"}
            )
        )

    def test_password_is_visible_and_not_getpass(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8")
        self.assertIn('input("Proxy (VISIBLE host:port:user:pass): ")', source)
        self.assertNotIn("getpass.getpass", source)
        self.assertNotIn("import getpass", source)

    def test_every_attempt_is_printed_live(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8")
        self.assertIn("checking IP/operator", source)
        self.assertIn("SELECTED:", source)

    def test_no_browser_runtime_dependency(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8").lower()
        for token in (
            "from playwright",
            "import playwright",
            "selenium",
            "chromium.launch",
            "sync_playwright(",
        ):
            self.assertNotIn(token, source)

    def test_credentials_not_persisted(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8")
        self.assertIn('"credentials_persisted": False', source)
        self.assertNotIn('"proxy_password": proxy_password', source)
        self.assertNotIn('"proxy_user": proxy_user', source)

    def test_runner_is_exact_c18(self):
        runner = (ROOT / "tests" / "RUN_OZON_CLAUDE_MOBILE_PROXY_C18.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools\\mobile_proxy.py --tries 15", runner)
        self.assertIn("PASSWORD INPUT IS VISIBLE", runner)


if __name__ == "__main__":
    unittest.main()
