from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import mobile_proxy


class MobileProxySelectorTests(unittest.TestCase):
    def test_rotate_session_from_bare_login(self):
        user, sid = mobile_proxy.rotate_session("abc-mobile-country-RU", "deadbeef")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-deadbeef")
        self.assertEqual(sid, "deadbeef")

    def test_rotate_session_replaces_existing_session(self):
        user, _ = mobile_proxy.rotate_session(
            "abc-mobile-country-RU-hold-session-session-old123", "new456"
        )
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-new456")
        self.assertNotIn("old123", user)

    def test_rotate_session_from_hold_form(self):
        user, _ = mobile_proxy.rotate_session("abc-mobile-country-RU-hold-session", "abc123")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-abc123")

    def test_rotate_session_from_hold_session_form_without_id(self):
        user, _ = mobile_proxy.rotate_session("abc-mobile-country-RU-hold-session-session", "abc123")
        self.assertEqual(user, "abc-mobile-country-RU-hold-session-session-abc123")

    def test_operator_detection_known_aliases(self):
        samples = [
            ({"isp": "MTS PJSC"}, "MTS"),
            ({"org": "PJSC VimpelCom"}, "BEELINE"),
            ({"asName": "MegaFon"}, "MEGAFON"),
            ({"asname": "MegaFon"}, "MEGAFON"),
            ({"carrier": "T2 Mobile"}, "TELE2_T2"),
            ({"network": "Scartel Ltd"}, "YOTA"),
        ]
        for payload, expected in samples:
            with self.subTest(payload=payload):
                operator, evidence = mobile_proxy._operator_evidence(payload)
                self.assertEqual(operator, expected)
                self.assertTrue(evidence)

    def test_unknown_operator_does_not_pass(self):
        operator, _ = mobile_proxy._operator_evidence({"isp": "Unknown Telecom"})
        self.assertIsNone(operator)

    def test_proxy_auth_detection(self):
        self.assertTrue(
            mobile_proxy._transport_auth_failed(
                {"status_code": 407, "message": "HTTP 407", "adapter_detail": "curl_cffi"}
            )
        )
        self.assertTrue(
            mobile_proxy._transport_auth_failed(
                {"status_code": None, "message": "CONNECT tunnel failed, response 407", "adapter_detail": "proxy"}
            )
        )
        self.assertFalse(
            mobile_proxy._transport_auth_failed(
                {"status_code": 200, "message": "HTTP 200", "adapter_detail": "curl_cffi"}
            )
        )

    def test_password_input_is_visible_diagnostic_mode(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8")
        self.assertNotIn("getpass.getpass", source)
        self.assertIn('input("Proxy password (VISIBLE, not saved): ")', source)

    def test_no_browser_runtime_dependency(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "from playwright",
            "import playwright",
            "selenium",
            "chromium.launch",
            "sync_playwright(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_credentials_are_not_part_of_report_contract(self):
        source = (TOOLS / "mobile_proxy.py").read_text(encoding="utf-8")
        self.assertIn('"credentials_persisted": False', source)
        self.assertNotIn('"proxy_password": proxy_password', source)
        self.assertNotIn('"proxy_user": proxy_user', source)


if __name__ == "__main__":
    unittest.main()
