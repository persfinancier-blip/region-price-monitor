from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

from input_models import CityRecord, normalize_city_record

SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5", "socks5h"}
_AUTH_URI_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@\s]+@)")


class ProxyContextError(ValueError):
    pass


def redact_transport_text(text: Any, *, secrets: tuple[str, ...] = ()) -> str:
    safe = str(text)
    safe = _AUTH_URI_RE.sub(lambda m: m.group("scheme") + "***@", safe)
    for secret in secrets:
        if secret:
            safe = safe.replace(str(secret), "***")
            safe = safe.replace(quote(str(secret), safe=""), "***")
    return safe


@dataclass(frozen=True, repr=False)
class BrowserProxyProjection:
    """SG02-owned credential projection; SG04 owns browser-specific adaptation."""

    city: str
    scheme: str
    host: str
    port: int
    username: str
    password: str

    @property
    def endpoint(self) -> str:
        user = quote(self.username, safe="")
        password = quote(self.password, safe="")
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return urlunsplit((self.scheme, f"{user}:{password}@{host}:{self.port}", "", "", ""))

    @property
    def safe_identity(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"{self.city}@{self.scheme}://{host}:{self.port}"

    def __repr__(self) -> str:
        return f"BrowserProxyProjection(city={self.city!r}, safe_identity={self.safe_identity!r})"


@dataclass(frozen=True, repr=False)
class ProxyContext:
    city: str
    scheme: str
    host: str
    port: int
    proxy_user: str
    proxy_password: str

    @classmethod
    def from_city(
        cls,
        city: CityRecord | Mapping[str, Any],
        *,
        default_scheme: str = "http",
    ) -> "ProxyContext":
        record = normalize_city_record(city)
        proxy = record.proxy.strip()
        if "://" not in proxy:
            proxy = f"{default_scheme}://{proxy}"
        parsed = urlsplit(proxy)
        scheme = parsed.scheme.lower()
        if scheme not in SUPPORTED_PROXY_SCHEMES:
            raise ProxyContextError(f"unsupported proxy scheme '{parsed.scheme}'")
        if parsed.username is not None or parsed.password is not None:
            raise ProxyContextError("proxy address must not contain embedded credentials")
        if not parsed.hostname:
            raise ProxyContextError("proxy host is missing")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ProxyContextError("proxy port is malformed") from exc
        if port is None:
            raise ProxyContextError("proxy port is required")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ProxyContextError("proxy address must contain only scheme, host and port")
        return cls(
            city=record.city,
            scheme=scheme,
            host=parsed.hostname,
            port=port,
            proxy_user=record.proxy_user,
            proxy_password=record.proxy_password,
        )

    @property
    def endpoint(self) -> str:
        user = quote(self.proxy_user, safe="")
        password = quote(self.proxy_password, safe="")
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        netloc = f"{user}:{password}@{host}:{self.port}"
        return urlunsplit((self.scheme, netloc, "", "", ""))

    @property
    def safe_identity(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"{self.city}@{self.scheme}://{host}:{self.port}"

    def requests_proxies(self) -> dict[str, str]:
        endpoint = self.endpoint
        return {"http": endpoint, "https": endpoint}

    def browser_projection(self) -> BrowserProxyProjection:
        return BrowserProxyProjection(
            city=self.city,
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            username=self.proxy_user,
            password=self.proxy_password,
        )

    def redact(self, value: Any) -> str:
        return redact_transport_text(value, secrets=(self.proxy_user, self.proxy_password))

    def __repr__(self) -> str:
        return f"ProxyContext(city={self.city!r}, safe_identity={self.safe_identity!r})"


class TransportKind(str, Enum):
    SUCCESS = "success"
    PROXY_AUTH_ERROR = "proxy_auth_error"
    PROXY_CONNECTION_ERROR = "proxy_connection_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    HTTP_ERROR = "http_error"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True, repr=False)
class TransportOutcome:
    kind: TransportKind
    status_code: int | None = None
    body: str | bytes | None = None
    headers: Mapping[str, Any] | None = None
    message: str | None = None
    adapter_detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.kind is TransportKind.SUCCESS

    @classmethod
    def from_http(
        cls,
        status_code: int,
        *,
        body: str | bytes | None = None,
        headers: Mapping[str, Any] | None = None,
        message: str | None = None,
        context: ProxyContext | None = None,
        adapter_detail: str | None = None,
    ) -> "TransportOutcome":
        if status_code == 407:
            kind = TransportKind.PROXY_AUTH_ERROR
        elif 200 <= status_code < 400:
            kind = TransportKind.SUCCESS
        else:
            kind = TransportKind.HTTP_ERROR
        safe_message = context.redact(message) if context and message else message
        safe_detail = context.redact(adapter_detail) if context and adapter_detail else adapter_detail
        return cls(
            kind=kind,
            status_code=status_code,
            body=body,
            headers=headers,
            message=safe_message,
            adapter_detail=safe_detail,
        )

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        context: ProxyContext | None = None,
        adapter_detail: str | None = None,
    ) -> "TransportOutcome":
        name = type(exc).__name__.lower()
        raw = str(exc)
        low = f"{name} {raw}".lower()
        if "407" in low or ("proxy" in low and ("auth" in low or "credential" in low)):
            kind = TransportKind.PROXY_AUTH_ERROR
        elif "proxy" in low:
            kind = TransportKind.PROXY_CONNECTION_ERROR
        elif "timeout" in low or "timed out" in low:
            kind = TransportKind.TIMEOUT
        elif any(token in low for token in ("connection", "connect", "dns", "name resolution", "ssl", "tls")):
            kind = TransportKind.CONNECTION_ERROR
        else:
            kind = TransportKind.UNEXPECTED_ERROR
        safe_message = context.redact(raw) if context else redact_transport_text(raw)
        safe_detail = context.redact(adapter_detail) if context and adapter_detail else adapter_detail
        return cls(kind=kind, message=safe_message, adapter_detail=safe_detail)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ok": self.ok,
            "status_code": self.status_code,
            "message": self.message,
            "adapter_detail": self.adapter_detail,
        }

    def __repr__(self) -> str:
        return (
            "TransportOutcome("
            f"kind={self.kind.value!r}, status_code={self.status_code!r}, "
            f"message={self.message!r}, adapter_detail={self.adapter_detail!r})"
        )
