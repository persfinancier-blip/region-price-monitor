from __future__ import annotations

from typing import Any, Callable

import requests

from transport import ProxyContext, TransportOutcome


class RequestsTransportError(ValueError):
    pass


def request_via_proxy(
    context: ProxyContext,
    method: str,
    url: str,
    *,
    params: Any = None,
    headers: Any = None,
    timeout: Any = None,
    request_func: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> TransportOutcome:
    """Execute exactly one requests call through the supplied ProxyContext.

    There is deliberately no direct-network retry/fallback path. Marketplace
    semantics remain with the caller; this function only returns transport facts.
    """
    if not isinstance(context, ProxyContext):
        raise RequestsTransportError("ProxyContext is required")
    if "proxies" in kwargs:
        raise RequestsTransportError("caller-supplied proxies are forbidden; ProxyContext is the authority")

    call = request_func or requests.request
    try:
        response = call(
            method.upper(),
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            proxies=context.requests_proxies(),
            **kwargs,
        )
    except Exception as exc:
        return TransportOutcome.from_exception(
            exc,
            context=context,
            adapter_detail=f"requests:{type(exc).__name__}",
        )

    return TransportOutcome.from_http(
        int(response.status_code),
        body=getattr(response, "text", None),
        headers=dict(getattr(response, "headers", {}) or {}),
        message=f"HTTP {response.status_code}",
        context=context,
        adapter_detail="requests",
    )
