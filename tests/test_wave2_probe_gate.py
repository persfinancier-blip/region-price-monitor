from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from transport import ProxyContext, TransportOutcome

SPEC = importlib.util.spec_from_file_location("probe_wave2_live", ROOT / "tools" / "probe_wave2_live.py")
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class Wave2ProbeGateTests(unittest.TestCase):
    def _context(self, city: str = "Novosibirsk") -> ProxyContext:
        return ProxyContext.from_city(
            {
                "city": city,
                "proxy": "https://proxy.example:443",
                "proxy_user": "user",
                "proxy_password": "pass",
            },
            require_explicit_scheme=True,
        )

    @staticmethod
    def _body(city: str, ip: str = "203.0.113.10") -> str:
        return json.dumps(
            {
                "query": ip,
                "countryCode": "RU",
                "regionName": "Novosibirsk Oblast" if city == "Novosibirsk" else "Moscow",
                "city": city,
                "mobile": True,
                "proxy": False,
                "hosting": False,
            }
        )

    def test_neutral_probe_uses_documented_ipn_json_api(self):
        self.assertEqual(probe.NEUTRAL_PROXY_CHECK_URL, "https://api.i.pn/json/")

    def test_ip_identity_keeps_only_safe_location_fields(self):
        identity = probe._ip_identity(self._body("Novosibirsk"))
        self.assertEqual(identity["city"], "Novosibirsk")
        self.assertEqual(identity["countryCode"], "RU")
        self.assertTrue(identity["mobile"])
        self.assertEqual(
            set(identity),
            {"query", "countryCode", "regionName", "city", "mobile", "proxy", "hosting"},
        )

    def test_ip_identity_accepts_bom_and_wrapped_json(self):
        body = "\ufeffprovider-result:\n" + self._body("Novosibirsk") + "\nend"
        identity = probe._ip_identity(body)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["city"], "Novosibirsk")

    def test_three_stack_egress_confirmation_passes_even_with_human_alias_label(self):
        context = self._context("nvs")
        body = self._body("Novosibirsk")
        native = {
            "available": True,
            "ok": True,
            "returncode": 0,
            "stderr": None,
            "identity": probe._ip_identity(body),
        }
        success = TransportOutcome.from_http(200, body=body, context=context)
        with patch.object(probe, "_native_curl_proxy_check", return_value=native), patch.object(
            probe, "requests_request", return_value=success
        ), patch.object(probe, "curl_request", return_value=success), patch.object(
            probe, "_save_neutral_body", return_value="local-only"
        ):
            result = probe._proxy_self_check(context)
        self.assertEqual(result["preliminary_gate"], "PROXY_EGRESS_CONTEXT_CONFIRMED_ALL_STACKS")
        self.assertTrue(result["all_transport_ok"])
        self.assertTrue(result["all_egress_locations_agree"])
        self.assertEqual(result["observed_egress_city"], "Novosibirsk")
        self.assertFalse(result["city_label_matches_egress"])

    def test_egress_mismatch_fails_closed_even_when_all_transports_are_200(self):
        context = self._context()
        good_body = self._body("Novosibirsk")
        wrong_body = self._body("Moscow", "203.0.113.20")
        native = {
            "available": True,
            "ok": True,
            "returncode": 0,
            "stderr": None,
            "identity": probe._ip_identity(good_body),
        }
        requests_success = TransportOutcome.from_http(200, body=good_body, context=context)
        curl_success = TransportOutcome.from_http(200, body=wrong_body, context=context)
        with patch.object(probe, "_native_curl_proxy_check", return_value=native), patch.object(
            probe, "requests_request", return_value=requests_success
        ), patch.object(probe, "curl_request", return_value=curl_success), patch.object(
            probe, "_save_neutral_body", return_value="local-only"
        ):
            result = probe._proxy_self_check(context)
        self.assertEqual(result["preliminary_gate"], "PROXY_EGRESS_CONTEXT_MISMATCH")
        self.assertTrue(result["all_transport_ok"])
        self.assertFalse(result["all_egress_locations_agree"])

    def test_native_reference_failure_blocks_confirmation(self):
        context = self._context()
        body = self._body("Novosibirsk")
        native = {"available": True, "ok": False, "returncode": 7, "stderr": "failed"}
        success = TransportOutcome.from_http(200, body=body, context=context)
        with patch.object(probe, "_native_curl_proxy_check", return_value=native), patch.object(
            probe, "requests_request", return_value=success
        ), patch.object(probe, "curl_request", return_value=success), patch.object(
            probe, "_save_neutral_body", return_value="local-only"
        ):
            result = probe._proxy_self_check(context)
        self.assertEqual(result["preliminary_gate"], "PROVIDER_REFERENCE_CURL_FAILED")
        self.assertFalse(result["all_transport_ok"])


if __name__ == "__main__":
    unittest.main()
