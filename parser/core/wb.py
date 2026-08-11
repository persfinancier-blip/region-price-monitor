# -*- coding: utf-8 -*-
"""Wildberries current batch parser bound to SG02 ProxyContext transport."""
from __future__ import annotations

import json
import time
from decimal import Decimal

from config import WB_API_URL, WB_HEADERS
from requests_transport import request_via_proxy
from transport import ProxyContext, TransportKind, TransportOutcome


def _failure_row(outcome: TransportOutcome) -> dict:
    return {
        "transport_error": outcome.safe_dict(),
        "source": "wb-transport",
    }


def fetch_prices_batch(skus, dest, proxy_context: ProxyContext, max_retries=3):
    """Return current WB semantic rows or one explicit transport-error row.

    SG03 still owns final optional-dest and stock semantics. This function keeps
    the existing price parser intact while ensuring every HTTP attempt uses the
    supplied ProxyContext and never falls back to direct networking.
    """
    if not skus:
        return []
    if not isinstance(proxy_context, ProxyContext):
        outcome = TransportOutcome.from_exception(
            ValueError("WB primary transport requires ProxyContext"),
            adapter_detail="wb",
        )
        return [_failure_row(outcome)]

    params = {
        "appType": 1,
        "curr": "rub",
        "dest": dest,
        "spp": 30,
        "nm": ";".join(str(s) for s in skus),
    }

    for attempt in range(max_retries):
        outcome = request_via_proxy(
            proxy_context,
            "GET",
            WB_API_URL,
            params=params,
            headers=WB_HEADERS,
            timeout=15,
        )
        if outcome.kind is TransportKind.HTTP_ERROR and outcome.status_code == 429:
            if attempt + 1 < max_retries:
                time.sleep(2 ** attempt + 1)
                continue
            return [_failure_row(outcome)]
        if not outcome.ok:
            return [_failure_row(outcome)]

        try:
            data = json.loads(outcome.body or "{}")
        except Exception as exc:
            parse_failure = TransportOutcome.from_exception(
                exc,
                context=proxy_context,
                adapter_detail="wb-response-json",
            )
            return [_failure_row(parse_failure)]

        raw = data.get("data")
        products = raw.get("products") if isinstance(raw, dict) else data.get("products")
        results = []
        for p in (products or []):
            sku = str(p.get("id"))
            sizes = p.get("sizes") or []
            if not sizes:
                continue
            price_obj = sizes[0].get("price") or {}
            price = Decimal(str(price_obj.get("product", 0))) / 100
            base = Decimal(str(price_obj.get("basic", 0))) / 100
            results.append({
                "sku": sku,
                "price": float(price),
                "price_base": float(base),
                "currency": "RUB",
                "is_available": price > 0,
                "source": "wb-api",
            })
        return results

    return [_failure_row(TransportOutcome.from_exception(RuntimeError("WB retry loop exhausted"), context=proxy_context))]
