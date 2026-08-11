# -*- coding: utf-8 -*-
"""Ozon current curl_cffi parser bound to SG02 ProxyContext transport.

SG04 still owns cookie-free regional bootstrap/context verification. This module
preserves the current cookie/price semantics while routing every curl network
call through one city-bound ProxyContext and surfacing transport failures.
"""
from __future__ import annotations

import json
import re

from config import OZON_STRATEGIES, DEBUG_DIR
from curl_transport import request_via_proxy
from transport import ProxyContext, TransportOutcome


def _num(t):
    if t is None:
        return None
    c = re.sub(r"[^\d.,]", "", str(t)).replace(" ", "").replace(",", ".")
    try:
        v = float(c)
        return v if v > 0 else None
    except Exception:
        return None


def parse_price(html):
    """Цена нужного SKU из состояния виджета webPrice (он на странице один)."""
    m = re.search(r'id="state-webPrice-[^"]*"\s+data-state=\'([^\']*)\'', html)
    if not m:
        return None
    try:
        st = json.loads(m.group(1))
    except Exception:
        return None
    card = _num(st.get("cardPrice"))
    reg = _num(st.get("price"))
    orig = _num(st.get("originalPrice"))
    price = card or reg
    if not price:
        return None
    return {
        "price": price,
        "price_card": card,
        "price_regular": reg,
        "price_original": orig,
        "price_base": orig or reg,
        "currency": "RUB",
        "is_available": bool(st.get("isAvailable", True)),
        "source": "webPrice-state",
    }


def _transport_failure(sku, outcome: TransportOutcome):
    return {
        "sku": sku,
        "transport_error": outcome.safe_dict(),
    }


def fetch_price(sku, cookies_list, proxy_context: ProxyContext, save_debug=False):
    """Current cookie-based Ozon path, transport-bound to ProxyContext.

    No direct/no-proxy retry exists. Cookie removal and autonomous requested-city
    bootstrap are deliberately deferred to SG04.
    """
    if not isinstance(proxy_context, ProxyContext):
        return _transport_failure(
            sku,
            TransportOutcome.from_exception(
                ValueError("Ozon primary HTTP transport requires ProxyContext"),
                adapter_detail="ozon",
            ),
        )

    from curl_cffi import requests as creq  # imported only when Ozon is invoked

    url = f"https://www.ozon.ru/product/{sku}/"
    last_failure: TransportOutcome | None = None

    for imp, use_session in OZON_STRATEGIES:
        if use_session:
            session = creq.Session(impersonate=imp)
            for c in cookies_list:
                dom = c.get("domain", ".ozon.ru").lstrip(".")
                session.cookies.set(c["name"], c["value"], domain=dom, path=c.get("path", "/"))
            warm = request_via_proxy(
                proxy_context,
                "GET",
                "https://www.ozon.ru/",
                session=session,
                timeout=15,
            )
            if not warm.ok:
                last_failure = warm
                continue
            outcome = request_via_proxy(
                proxy_context,
                "GET",
                url,
                session=session,
                timeout=30,
            )
        else:
            cookie_dict = {c["name"]: c["value"] for c in cookies_list}
            warm = request_via_proxy(
                proxy_context,
                "GET",
                "https://www.ozon.ru/",
                client=creq,
                cookies=cookie_dict,
                impersonate=imp,
                timeout=15,
            )
            if not warm.ok:
                last_failure = warm
                continue
            outcome = request_via_proxy(
                proxy_context,
                "GET",
                url,
                client=creq,
                cookies=cookie_dict,
                impersonate=imp,
                timeout=30,
            )

        if not outcome.ok:
            last_failure = outcome
            continue

        html = outcome.body.decode("utf-8", errors="replace") if isinstance(outcome.body, bytes) else (outcome.body or "")
        if save_debug:
            (DEBUG_DIR / f"ozon_200_{sku}.html").write_text(html, encoding="utf-8")
        result = parse_price(html)
        if result:
            result["sku"] = sku
            return result
        return {"sku": sku, "error": "200_no_price"}

    if last_failure is not None:
        return _transport_failure(sku, last_failure)
    return _transport_failure(
        sku,
        TransportOutcome.from_exception(RuntimeError("Ozon strategies exhausted"), context=proxy_context),
    )


def load_cookies(profile_dir):
    from pathlib import Path

    ck = Path(profile_dir) / "cookies.json"
    if not ck.exists():
        return None
    return json.loads(ck.read_text(encoding="utf-8"))
