from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import curl_transport
import requests_transport
from transport import ProxyContext, ProxyContextError


class _Response:
    status_code = 200
    text = "ok"
    headers = {}


class _CurlClient:
    def __init__(self):
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return _Response()


class Wave2ExplicitSchemeTests(unittest.TestCase):
    def _city(self, proxy: str):
        return {
            "city": "Novosibirsk",
            "proxy": proxy,
            "proxy_user": "user",
            "proxy_password": "pass",
        }

    def test_strict_live_mode_rejects_scheme_less_proxy(self):
        with self.assertRaises(ProxyContextError) as ctx:
            ProxyContext.from_city(
                self._city("proxy.example:443"),
                require_explicit_scheme=True,
            )
        self.assertIn("scheme is required", str(ctx.exception))

    def test_legacy_non_strict_host_port_still_defaults_http(self):
        context = ProxyContext.from_city(self._city("proxy.example:8080"))
        self.assertEqual(context.scheme, "http")

    def test_explicit_https_is_preserved_in_requests_adapter(self):
        context = ProxyContext.from_city(
            self._city("https://proxy.example:443"),
            require_explicit_scheme=True,
        )
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append(kwargs)
            return _Response()

        outcome = requests_transport.request_via_proxy(
            context,
            "GET",
            "https://example.test/",
            request_func=fake_request,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["proxies"]["https"].startswith("https://user:pass@proxy.example:443"))
        self.assertTrue(calls[0]["proxies"]["http"].startswith("https://user:pass@proxy.example:443"))

    def test_explicit_https_is_preserved_in_curl_adapter(self):
        context = ProxyContext.from_city(
            self._city("https://proxy.example:443"),
            require_explicit_scheme=True,
        )
        client = _CurlClient()
        outcome = curl_transport.request_via_proxy(
            context,
            "GET",
            "https://example.test/",
            client=client,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(client.kwargs["proxy"], "https://proxy.example:443")
        self.assertEqual(client.kwargs["proxy_auth"], ("user", "pass"))

    def test_browser_projection_preserves_explicit_https(self):
        context = ProxyContext.from_city(
            self._city("https://proxy.example:443"),
            require_explicit_scheme=True,
        )
        projection = context.browser_projection()
        self.assertEqual(projection.scheme, "https")
        self.assertEqual(projection.safe_identity, "Novosibirsk@https://proxy.example:443")


if __name__ == "__main__":
    unittest.main()
