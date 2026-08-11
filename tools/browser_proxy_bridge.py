from __future__ import annotations

import base64
import select
import socket
import socketserver
import ssl
import threading
from typing import Any

from transport import ProxyContext

_MAX_HEADER_BYTES = 64 * 1024
_CONNECT_TIMEOUT_S = 15
_IDLE_TIMEOUT_S = 45


class BrowserProxyBridgeError(RuntimeError):
    pass


def _read_headers(sock: socket.socket, *, limit: int = _MAX_HEADER_BYTES) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > limit:
            raise BrowserProxyBridgeError("proxy header exceeded bounded limit")
    return bytes(data)


def _request_method(header: bytes) -> str:
    try:
        first = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
        method, _target, _version = first.split(" ", 2)
    except Exception as exc:
        raise BrowserProxyBridgeError("malformed browser proxy request") from exc
    return method.upper()


def _parse_connect_target(header: bytes) -> tuple[str, int, str]:
    try:
        first = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
        method, target, _version = first.split(" ", 2)
    except Exception as exc:
        raise BrowserProxyBridgeError("malformed browser proxy request") from exc
    if method.upper() != "CONNECT":
        raise BrowserProxyBridgeError("CONNECT request required")
    if target.startswith("["):
        end = target.find("]")
        if end < 0 or end + 2 > len(target) or target[end + 1] != ":":
            raise BrowserProxyBridgeError("malformed IPv6 CONNECT target")
        host = target[1:end]
        port_text = target[end + 2 :]
    else:
        try:
            host, port_text = target.rsplit(":", 1)
        except ValueError as exc:
            raise BrowserProxyBridgeError("CONNECT target missing port") from exc
    try:
        port = int(port_text)
    except ValueError as exc:
        raise BrowserProxyBridgeError("CONNECT target has malformed port") from exc
    if not host or port <= 0 or port > 65535:
        raise BrowserProxyBridgeError("CONNECT target is invalid")
    return host, port, target


def _connect_upstream(context: ProxyContext) -> socket.socket:
    raw = socket.create_connection((context.host, context.port), timeout=_CONNECT_TIMEOUT_S)
    if context.scheme == "http":
        return raw
    if context.scheme != "https":
        raw.close()
        raise BrowserProxyBridgeError(
            f"browser evidence bridge supports http/https upstream proxies, not {context.scheme!r}"
        )
    tls_context = ssl.create_default_context()
    try:
        return tls_context.wrap_socket(raw, server_hostname=context.host)
    except Exception:
        raw.close()
        raise


def _upstream_connect_request(context: ProxyContext, target: str) -> bytes:
    token = base64.b64encode(
        f"{context.proxy_user}:{context.proxy_password}".encode("utf-8")
    ).decode("ascii")
    return (
        f"CONNECT {target} HTTP/1.1\r\n"
        f"Host: {target}\r\n"
        f"Proxy-Authorization: Basic {token}\r\n"
        "Proxy-Connection: Keep-Alive\r\n"
        "\r\n"
    ).encode("ascii")


def _status_code(header: bytes) -> int | None:
    try:
        first = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        return int(first.split(" ", 2)[1])
    except Exception:
        return None


def _relay(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, _IDLE_TIMEOUT_S)
        if exceptional or not readable:
            return
        for source in readable:
            destination = right if source is left else left
            try:
                data = source.recv(64 * 1024)
            except (BlockingIOError, ssl.SSLWantReadError):
                continue
            if not data:
                return
            destination.sendall(data)


class _BridgeServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], context: ProxyContext):
        self.proxy_context = context
        self.last_error: str | None = None
        super().__init__(address, _BridgeHandler)

    def record_error(self, exc: BaseException) -> None:
        self.last_error = self.proxy_context.redact(f"{type(exc).__name__}: {exc}")


class _BridgeHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _BridgeServer)
        context = server.proxy_context
        upstream: socket.socket | None = None
        try:
            browser_header = _read_headers(self.request)
            method = _request_method(browser_header)
            if method != "CONNECT":
                # Chrome may emit background plain-HTTP connectivity/time probes even when
                # the target marketplace navigation is HTTPS. They are not part of the
                # bounded evidence path and must not poison last_error or become a second
                # proxy-routing authority.
                self.request.sendall(
                    b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
                return

            _host, _port, target = _parse_connect_target(browser_header)
            upstream = _connect_upstream(context)
            upstream.sendall(_upstream_connect_request(context, target))
            upstream_header = _read_headers(upstream)
            status = _status_code(upstream_header)
            if status != 200:
                # Preserve provider HTTP status for Chrome while never surfacing credentials.
                self.request.sendall(upstream_header or b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                return
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _relay(self.request, upstream)
        except Exception as exc:
            server.record_error(exc)
            try:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:
                    pass


class LocalBrowserProxyBridge:
    """One-process loopback CONNECT bridge derived only from one ProxyContext.

    Chrome receives an unauthenticated localhost HTTP proxy URL. The bridge applies
    the upstream scheme/host/port/Basic auth from the supplied ProxyContext and has
    no separate credential/config authority. It exists only for bounded browser
    evidence/bootstrap work. Incidental plain-HTTP Chrome background probes are
    answered locally and are not forwarded or treated as evidence failures.
    """

    def __init__(self, context: ProxyContext):
        if not isinstance(context, ProxyContext):
            raise BrowserProxyBridgeError("ProxyContext is required")
        self._context = context
        self._server: _BridgeServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def proxy_url(self) -> str:
        if self._server is None:
            raise BrowserProxyBridgeError("browser bridge is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def last_error(self) -> str | None:
        return self._server.last_error if self._server is not None else None

    @property
    def safe_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "running": self._server is not None,
            "upstream": self._context.safe_identity,
        }
        if self._server is not None:
            state["loopback_proxy"] = self.proxy_url
            state["last_error"] = self.last_error
        return state

    def start(self) -> "LocalBrowserProxyBridge":
        if self._server is not None:
            return self
        server = _BridgeServer(("127.0.0.1", 0), self._context)
        thread = threading.Thread(target=server.serve_forever, name="wave2-browser-proxy", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def close(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)

    def __enter__(self) -> "LocalBrowserProxyBridge":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"LocalBrowserProxyBridge(upstream={self._context.safe_identity!r}, running={self._server is not None})"
