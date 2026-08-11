# -*- coding: utf-8 -*-
"""Ozon readers.

SG04 primary:
    ProxyContext -> direct entrypoint JSON -> exact SKU price or typed challenge/error.

SG05 legacy fallback:
    explicit invocation only -> personalized authenticated cookies/profile ->
    legacy curl_cffi HTML reader. Proxy remains optional for compatibility with
    the original working mechanism.

No primary failure silently enters the legacy path.
"""
from __future__ import annotations

import json
import re
from typing import Any

from config import OZON_STRATEGIES, DEBUG_DIR
from curl_transport import request_via_proxy
from transport import ProxyContext, TransportOutcome

OZON_ENTRYPOINT_API = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
OZON_ENTRYPOINT_IMPERSONATE = ("chrome", "chrome146", "chrome145", "chrome142", "chrome136")
OZON_ENTRYPOINT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Content-Type": "application/json",
    "x-o3-app-name": "dweb_client",
    "x-o3-app-version": "release_24-6-2026_e801a3c6",
    "x-o3-manifest-version": (
        "frontend-ozon-ru:e801a3c62f8cfe341954419adfaa354dbaadf626,"
        "search-render-api:26877a5f1f6b92f5ef5a217ade8a0b151a885ecf,"
        "checkout-render-api:aecd1b3959ca8606f0af760c8123d37b48cc83e3,"
        "fav-render-api:59a97bd983119f6dddc92804adb6bad00256ce1b,"
        "pdp-render-api:c21f15997cdd645d082b0ef09089ca47e19990b7,"
        "sf-render-api:6b9533d13dc9cafbc4e33224af37432d468c316c"
    ),
}
_CHALLENGE_KEYS = {
    "captchaURL",
    "blockURL",
    "challengeURL",
    "incidentId",
    "supportURL",
    "timeoutSec",
}


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
    """Legacy HTML: exact webPrice widget for the requested product page."""
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


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _decode_json(body: Any) -> dict[str, Any] | None:
    text = _body_text(body)
    if not text:
        return None
    try:
        value = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _widget_json(value: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_challenge(payload: dict[str, Any]) -> bool:
    return bool(_CHALLENGE_KEYS.intersection(payload.keys())) and "widgetStates" not in payload


def _parse_entrypoint_price(payload: dict[str, Any], sku: str) -> dict[str, Any]:
    if _is_challenge(payload):
        return {"ok": False, "error": "challenge"}

    page_info = payload.get("pageInfo")
    page_url = page_info.get("url") if isinstance(page_info, dict) else None
    if page_url and str(sku) not in str(page_url):
        return {"ok": False, "error": "wrong_product_page", "page_url": str(page_url)}

    states = payload.get("widgetStates")
    if not isinstance(states, dict) or not states:
        return {"ok": False, "error": "widget_states_missing", "page_url": page_url}

    layout = payload.get("layout")
    if isinstance(layout, list):
        for component_name in ("webPrice", "webSale"):
            for block in layout:
                if not isinstance(block, dict) or block.get("component") != component_name:
                    continue
                state_id = block.get("stateId")
                if not state_id or state_id not in states:
                    continue
                widget = _widget_json(states[state_id])
                price = _num(widget.get("price")) if widget else None
                if price:
                    return {
                        "ok": True,
                        "trusted": True,
                        "state_id": str(state_id),
                        "page_url": page_url,
                        "price": price,
                        "price_card": _num(widget.get("cardPrice")),
                        "price_regular": price,
                        "price_original": _num(widget.get("originalPrice")),
                        "price_base": _num(widget.get("originalPrice")) or price,
                        "currency": "RUB",
                        "is_available": bool(widget.get("isAvailable", True)),
                    }

    candidates: list[tuple[str, dict[str, Any], float]] = []
    for key, value in states.items():
        if "webPrice" not in str(key) and "webSale" not in str(key):
            continue
        widget = _widget_json(value)
        price = _num(widget.get("price")) if widget else None
        if widget and price:
            candidates.append((str(key), widget, price))

    if len(candidates) == 1:
        key, widget, price = candidates[0]
        return {
            "ok": True,
            "trusted": False,
            "state_id": key,
            "page_url": page_url,
            "price": price,
            "price_card": _num(widget.get("cardPrice")),
            "price_regular": price,
            "price_original": _num(widget.get("originalPrice")),
            "price_base": _num(widget.get("originalPrice")) or price,
            "currency": "RUB",
            "is_available": bool(widget.get("isAvailable", True)),
        }
    if len(candidates) > 1:
        unique_prices = {price for _, _, price in candidates}
        if len(unique_prices) == 1:
            key, widget, price = candidates[0]
            return {
                "ok": True,
                "trusted": False,
                "state_id": key,
                "page_url": page_url,
                "price": price,
                "price_card": _num(widget.get("cardPrice")),
                "price_regular": price,
                "price_original": _num(widget.get("originalPrice")),
                "price_base": _num(widget.get("originalPrice")) or price,
                "currency": "RUB",
                "is_available": bool(widget.get("isAvailable", True)),
            }
        return {
            "ok": False,
            "error": "ambiguous_price_widgets",
            "candidate_count": len(candidates),
        }
    return {"ok": False, "error": "price_widget_not_found", "page_url": page_url}


def _transport_failure(sku, outcome: TransportOutcome, *, path: str):
    return {
        "sku": str(sku),
        "status": "transport_error",
        "path": path,
        "transport_error": outcome.safe_dict(),
    }


def fetch_price_proxy_first(sku, proxy_context: ProxyContext):
    """SG04 primary: zero-cookie direct entrypoint through one ProxyContext.

    Returns status=price, challenge, parse_error or transport_error.
    It never invokes SG05 and never fabricates a zero price.
    """
    if not isinstance(proxy_context, ProxyContext):
        return _transport_failure(
            sku,
            TransportOutcome.from_exception(
                ValueError("Ozon SG04 primary requires ProxyContext"),
                adapter_detail="ozon-primary",
            ),
            path="sg04_proxy_first",
        )

    from curl_cffi import requests as creq

    headers = dict(OZON_ENTRYPOINT_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
    attempts: list[dict[str, Any]] = []
    saw_json = False

    for strategy in OZON_ENTRYPOINT_IMPERSONATE:
        outcome = request_via_proxy(
            proxy_context,
            "GET",
            OZON_ENTRYPOINT_API,
            client=creq,
            params={"url": f"/product/{sku}/"},
            headers=headers,
            impersonate=strategy,
            timeout=45,
            allow_redirects=True,
        )
        safe = outcome.safe_dict()
        payload = _decode_json(outcome.body)
        saw_json = saw_json or payload is not None
        attempt = {
            "strategy": strategy,
            "transport": safe,
            "json_decoded": payload is not None,
        }
        attempts.append(attempt)

        if payload is not None and _is_challenge(payload):
            return {
                "sku": str(sku),
                "status": "challenge",
                "path": "sg04_proxy_first",
                "strategy": strategy,
                "challenge": True,
                "challenge_url_present": bool(payload.get("captchaURL")),
                "attempts": attempts,
            }

        if payload is not None:
            parsed = _parse_entrypoint_price(payload, str(sku))
            if parsed.get("ok"):
                result = dict(parsed)
                result.pop("ok", None)
                result.update(
                    {
                        "sku": str(sku),
                        "status": "price",
                        "path": "sg04_proxy_first",
                        "source": "entrypoint-widget-state",
                        "strategy": strategy,
                    }
                )
                return result

        if not outcome.ok:
            continue

    if attempts and not saw_json:
        last = attempts[-1]["transport"]
        return {
            "sku": str(sku),
            "status": "transport_error",
            "path": "sg04_proxy_first",
            "transport_error": last,
            "attempts": attempts,
        }
    return {
        "sku": str(sku),
        "status": "parse_error",
        "path": "sg04_proxy_first",
        "error": "entrypoint_json_without_exact_price",
        "attempts": attempts,
    }


def fetch_price_legacy_authenticated(sku, cookies_list, proxy=None, save_debug=False):
    """SG05 explicit legacy path using personalized authenticated cookies.

    `proxy` is intentionally optional to preserve the original working reader.
    This function is not called by SG04 automatically.
    """
    if not cookies_list:
        return {
            "sku": str(sku),
            "status": "legacy_auth_missing",
            "path": "sg05_authenticated_legacy",
            "error": "authenticated_cookies_missing",
        }

    from curl_cffi import requests as creq

    proxies = {"https": proxy, "http": proxy} if proxy else None
    url = f"https://www.ozon.ru/product/{sku}/"
    last_status = None
    last_error = None

    for imp, use_session in OZON_STRATEGIES:
        try:
            if use_session:
                session = creq.Session(impersonate=imp)
                for cookie in cookies_list:
                    name = cookie.get("name")
                    if not name:
                        continue
                    domain = cookie.get("domain", ".ozon.ru").lstrip(".")
                    session.cookies.set(
                        name,
                        cookie.get("value", ""),
                        domain=domain,
                        path=cookie.get("path", "/"),
                    )
                session.get("https://www.ozon.ru/", proxies=proxies, timeout=15)
                response = session.get(url, proxies=proxies, timeout=30)
            else:
                cookie_dict = {
                    cookie["name"]: cookie.get("value", "")
                    for cookie in cookies_list
                    if cookie.get("name")
                }
                creq.get(
                    "https://www.ozon.ru/",
                    cookies=cookie_dict,
                    impersonate=imp,
                    proxies=proxies,
                    timeout=15,
                )
                response = creq.get(
                    url,
                    cookies=cookie_dict,
                    impersonate=imp,
                    proxies=proxies,
                    timeout=30,
                )

            last_status = int(response.status_code)
            if response.status_code == 200:
                if save_debug:
                    (DEBUG_DIR / f"ozon_200_{sku}.html").write_text(
                        response.text, encoding="utf-8"
                    )
                parsed = parse_price(response.text)
                if parsed:
                    parsed.update(
                        {
                            "sku": str(sku),
                            "status": "price",
                            "path": "sg05_authenticated_legacy",
                        }
                    )
                    return parsed
                return {
                    "sku": str(sku),
                    "status": "parse_error",
                    "path": "sg05_authenticated_legacy",
                    "error": "200_no_price",
                }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

    return {
        "sku": str(sku),
        "status": "legacy_rejected",
        "path": "sg05_authenticated_legacy",
        "error": "authenticated_session_rejected",
        "http_status": last_status,
        "detail": last_error,
    }


def fetch_price(
    sku,
    cookies_list,
    proxy=None,
    save_debug=False,
    proxy_context: ProxyContext | None = None,
):
    """Backward-compatible legacy entrypoint.

    Historical callers may still pass `proxy`; newer callers that already own a
    ProxyContext may pass it explicitly. The legacy path itself remains SG05.
    """
    if proxy_context is not None:
        proxy = proxy_context.endpoint
    return fetch_price_legacy_authenticated(
        sku,
        cookies_list,
        proxy=proxy,
        save_debug=save_debug,
    )


def read_price(
    sku,
    proxy_context: ProxyContext,
    *,
    allow_legacy_fallback: bool = False,
    legacy_cookies=None,
    legacy_proxy=None,
    save_debug=False,
):
    """Glue SG04 and SG05 behind one result contract.

    Primary always runs first. Legacy executes only when the caller explicitly
    sets allow_legacy_fallback=True, and only after a non-price primary result.
    """
    primary = fetch_price_proxy_first(sku, proxy_context)
    if primary.get("status") == "price" or not allow_legacy_fallback:
        return primary

    legacy = fetch_price_legacy_authenticated(
        sku,
        legacy_cookies,
        proxy=legacy_proxy,
        save_debug=save_debug,
    )
    result = dict(legacy)
    result["primary_status"] = primary.get("status")
    result["primary_path"] = primary.get("path")
    result["fallback_explicit"] = True
    return result


def load_cookies(profile_dir):
    from pathlib import Path

    ck = Path(profile_dir) / "cookies.json"
    if not ck.exists():
        return None
    return json.loads(ck.read_text(encoding="utf-8"))
