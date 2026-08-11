from __future__ import annotations

from typing import Any

from transport import ProxyContext, TransportOutcome


class CurlTransportError(ValueError):
    pass


def _curl_proxy_url(context: ProxyContext) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def request_via_proxy(
    context: ProxyContext,
    method: str,
    url: str,
    *,
    session: Any = None,
    client: Any = None,
    timeout: Any = None,
    impersonate: str | None = None,
    cookies: Any = None,
    **kwargs: Any,
) -> TransportOutcome:
    """Execute exactly one curl_cffi call through the supplied ProxyContext.

    curl_cffi receives the non-secret proxy URL separately from proxy_auth. This
    avoids asking libcurl to parse a generated credential-bearing URI while
    preserving ProxyContext as the single routing/auth authority. No direct
    fallback exists.
    """
    if not isinstance(context, ProxyContext):
        raise CurlTransportError("ProxyContext is required")
    for forbidden in ("proxy", "proxies", "proxy_auth"):
        if forbidden in kwargs:
            raise CurlTransportError(
                f"caller-supplied {forbidden} is forbidden; ProxyContext is the authority"
            )

    if session is None and client is None:
        from curl_cffi import requests as client  # type: ignore

    target = session if session is not None else client
    verb = method.lower().strip()
    call = getattr(target, verb, None)
    if call is None:
        generic = getattr(target, "request", None)
        if generic is None:
            raise CurlTransportError(f"curl target does not support method {method!r}")

        def call(url_: str, **call_kwargs: Any):
            return generic(method.upper(), url_, **call_kwargs)

    call_kwargs: dict[str, Any] = {
        "proxy": _curl_proxy_url(context),
        "proxy_auth": (context.proxy_user, context.proxy_password),
    }
    if timeout is not None:
        call_kwargs["timeout"] = timeout
    if cookies is not None:
        call_kwargs["cookies"] = cookies
    if impersonate is not None and session is None:
        call_kwargs["impersonate"] = impersonate
    call_kwargs.update(kwargs)

    try:
        response = call(url, **call_kwargs)
    except Exception as exc:
        return TransportOutcome.from_exception(
            exc,
            context=context,
            adapter_detail=f"curl_cffi:{type(exc).__name__}",
        )

    return TransportOutcome.from_http(
        int(response.status_code),
        body=getattr(response, "text", None),
        headers=dict(getattr(response, "headers", {}) or {}),
        message=f"HTTP {response.status_code}",
        context=context,
        adapter_detail="curl_cffi",
    )
