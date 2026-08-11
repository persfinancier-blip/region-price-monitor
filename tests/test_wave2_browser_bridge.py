from __future__ import annotations

import base64
from pathlib import Path
import socket
import socketserver
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge, _connect_upstream
from transport import ProxyContext


class _CaptureHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        self.server.captured = bytes(data)  # type: ignore[attr-defined]
        self.request.sendall(b"HTTP/1.1 502 Diagnostic Stop\r\nContent-Length: 0\r\n\r\n")


class _CaptureServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Wave2BrowserBridgeTests(unittest.TestCase):
    def _context(self, proxy: str, user: str = "u-ser", password: str = "p:ass") -> ProxyContext:
        return ProxyContext.from_city(
            {
                "city": "Novosibirsk",
                "proxy": proxy,
                "proxy_user": user,
                "proxy_password": password,
            },
            require_explicit_scheme=True,
        )

    def test_loopback_bridge_uses_same_context_basic_auth_and_safe_repr(self):
        upstream = _CaptureServer(("127.0.0.1", 0), _CaptureHandler)
        upstream.captured = b""  # type: ignore[attr-defined]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        host, port = upstream.server_address
        context = self._context(f"http://{host}:{port}")
        try:
            with LocalBrowserProxyBridge(context) as bridge:
                self.assertTrue(bridge.proxy_url.startswith("http://127.0.0.1:"))
                self.assertNotIn(context.proxy_user, repr(bridge))
                self.assertNotIn(context.proxy_password, repr(bridge))
                target_host, target_port = bridge.proxy_url.removeprefix("http://").split(":")
                with socket.create_connection((target_host, int(target_port)), timeout=3) as client:
                    client.sendall(
                        b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
                    )
                    response = client.recv(4096)
                self.assertIn(b"502 Diagnostic Stop", response)
            captured = upstream.captured.decode("ascii")  # type: ignore[attr-defined]
            expected = base64.b64encode(b"u-ser:p:ass").decode("ascii")
            self.assertIn("CONNECT example.com:443 HTTP/1.1", captured)
            self.assertIn(f"Proxy-Authorization: Basic {expected}", captured)
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=3)

    def test_https_upstream_is_tls_wrapped_with_context_host(self):
        context = self._context("https://proxy.example:443")
        raw = MagicMock()
        wrapped = MagicMock()
        tls_context = MagicMock()
        tls_context.wrap_socket.return_value = wrapped
        with patch("browser_proxy_bridge.socket.create_connection", return_value=raw) as create_conn, patch(
            "browser_proxy_bridge.ssl.create_default_context", return_value=tls_context
        ):
            result = _connect_upstream(context)
        self.assertIs(result, wrapped)
        create_conn.assert_called_once_with(("proxy.example", 443), timeout=15)
        tls_context.wrap_socket.assert_called_once_with(raw, server_hostname="proxy.example")

    def test_safe_state_never_contains_credentials(self):
        context = self._context("http://127.0.0.1:3128", user="secret-user", password="secret-pass")
        bridge = LocalBrowserProxyBridge(context)
        text = repr(bridge.safe_state)
        self.assertNotIn("secret-user", text)
        self.assertNotIn("secret-pass", text)


if __name__ == "__main__":
    unittest.main()
