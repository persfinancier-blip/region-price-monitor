from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import curl_transport
import ozon
import requests_transport
import wb
from transport import ProxyContext, TransportKind, TransportOutcome


class FakeResponse:
    def __init__(self, status_code=200, text="ok", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"x-test": "1"}


class FakeCookieJar:
    def __init__(self):
        self.values = []

    def set(self, *args, **kwargs):
        self.values.append((args, kwargs))


class FakeSession:
    def __init__(self):
        self.calls = []
        self.cookies = FakeCookieJar()

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(200, "session-ok")


class FakeCurlClient:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(200, "direct-ok")


class Wave2TransportTests(unittest.TestCase):
    def setUp(self):
        self.context = ProxyContext.from_city({
            "city": "Moscow",
            "proxy": "proxy.example:8080",
            "proxy_user": "user@corp",
            "proxy_password": "secret/pass",
        })

    def test_requests_adapter_applies_same_authenticated_endpoint_to_http_https(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(200, "body")

        outcome = requests_transport.request_via_proxy(
            self.context,
            "GET",
            "https://example.test/path",
            timeout=7,
            request_func=fake_request,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(len(calls), 1)
        proxies = calls[0][2]["proxies"]
        self.assertEqual(proxies, self.context.requests_proxies())
        self.assertEqual(proxies["http"], proxies["https"])
        self.assertIn("user%40corp", proxies["https"])
        self.assertIn("secret%2Fpass", proxies["https"])

    def test_requests_adapter_has_no_direct_fallback_and_redacts_failure(self):
        calls = []

        def failing_request(method, url, **kwargs):
            calls.append(kwargs)
            raise RuntimeError(f"proxy connection failed {self.context.endpoint}")

        outcome = requests_transport.request_via_proxy(
            self.context,
            "GET",
            "https://example.test/",
            request_func=failing_request,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(outcome.kind, TransportKind.PROXY_CONNECTION_ERROR)
        self.assertNotIn("secret/pass", outcome.message or "")
        self.assertNotIn("user@corp", outcome.message or "")

    def test_requests_adapter_rejects_second_proxy_authority(self):
        with self.assertRaises(requests_transport.RequestsTransportError):
            requests_transport.request_via_proxy(
                self.context,
                "GET",
                "https://example.test/",
                request_func=lambda *a, **k: FakeResponse(),
                proxies={"https": "http://other-proxy:1"},
            )

    def test_curl_adapter_direct_path_uses_proxy_context(self):
        client = FakeCurlClient()
        outcome = curl_transport.request_via_proxy(
            self.context,
            "GET",
            "https://example.test/",
            client=client,
            impersonate="edge",
            timeout=9,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(len(client.calls), 1)
        kwargs = client.calls[0][1]
        self.assertEqual(kwargs["proxies"], self.context.requests_proxies())
        self.assertEqual(kwargs["impersonate"], "edge")

    def test_curl_adapter_session_path_uses_proxy_context(self):
        session = FakeSession()
        outcome = curl_transport.request_via_proxy(
            self.context,
            "GET",
            "https://example.test/",
            session=session,
            timeout=9,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][1]["proxies"], self.context.requests_proxies())
        self.assertNotIn("impersonate", session.calls[0][1])

    def test_curl_adapter_rejects_second_proxy_authority(self):
        with self.assertRaises(curl_transport.CurlTransportError):
            curl_transport.request_via_proxy(
                self.context,
                "GET",
                "https://example.test/",
                client=FakeCurlClient(),
                proxies={"https": "http://other-proxy:1"},
            )

    def test_browser_projection_is_derived_from_context_and_safe_to_repr(self):
        projection = self.context.browser_projection()
        self.assertEqual(projection.city, self.context.city)
        self.assertEqual(projection.host, self.context.host)
        self.assertEqual(projection.port, self.context.port)
        self.assertEqual(projection.endpoint, self.context.endpoint)
        self.assertNotIn("secret/pass", repr(projection))
        self.assertNotIn("user@corp", repr(projection))

    def test_wb_collector_uses_shared_adapter_and_keeps_current_price_parser(self):
        body = '{"data":{"products":[{"id":123,"sizes":[{"price":{"product":12345,"basic":15000}}]}]}}'
        seen = []

        def fake_adapter(context, method, url, **kwargs):
            seen.append((context, method, url, kwargs))
            return TransportOutcome.from_http(200, body=body, context=context)

        with patch.object(wb, "request_via_proxy", side_effect=fake_adapter):
            result = wb.fetch_prices_batch([123], "-1257786", self.context)

        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0][0], self.context)
        self.assertEqual(result[0]["sku"], "123")
        self.assertEqual(result[0]["price"], 123.45)

    def test_wb_transport_failure_is_not_fake_empty_success(self):
        failure = TransportOutcome.from_exception(RuntimeError("proxy connection failed"), context=self.context)
        with patch.object(wb, "request_via_proxy", return_value=failure):
            result = wb.fetch_prices_batch([123], "-1257786", self.context)
        self.assertEqual(len(result), 1)
        self.assertIn("transport_error", result[0])
        self.assertFalse(result[0]["transport_error"]["ok"])

    def test_ozon_current_home_and_product_calls_share_same_context(self):
        html = "<html><div id=\"state-webPrice-x\" data-state='{" \
               "\"cardPrice\":\"1 234 ₽\",\"price\":\"1 300 ₽\",\"originalPrice\":\"1 500 ₽\"}'></div></html>"
        seen = []
        fake_session = FakeSession()

        def fake_adapter(context, method, url, **kwargs):
            seen.append((context, method, url, kwargs))
            body = "home" if url.rstrip("/") == "https://www.ozon.ru" else html
            return TransportOutcome.from_http(200, body=body, context=context)

        with patch("curl_cffi.requests.Session", return_value=fake_session), patch.object(
            ozon, "request_via_proxy", side_effect=fake_adapter
        ):
            result = ozon.fetch_price("777", [], self.context)

        self.assertGreaterEqual(len(seen), 2)
        self.assertTrue(all(call[0] is self.context for call in seen))
        self.assertEqual(result["sku"], "777")
        self.assertEqual(result["price"], 1234.0)

    def test_ozon_transport_failure_is_explicit(self):
        failure = TransportOutcome.from_exception(RuntimeError("proxy authentication 407"), context=self.context)
        fake_session = FakeSession()
        with patch("curl_cffi.requests.Session", return_value=fake_session), patch.object(
            ozon, "request_via_proxy", return_value=failure
        ):
            result = ozon.fetch_price("777", [], self.context)
        self.assertIn("transport_error", result)
        self.assertFalse(result["transport_error"]["ok"])


if __name__ == "__main__":
    unittest.main()
