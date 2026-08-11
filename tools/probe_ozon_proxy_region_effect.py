from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from curl_transport import request_via_proxy as curl_request_via_proxy
from input_models import InputValidationError
from transport import ProxyContext, ProxyContextError

API_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
NEUTRAL_URL = "https://api.i.pn/json/"
DEFAULT_SKU = "3129447770"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_proxy_region_effect_report.json"
DEFAULT_COOKIE_FILE = LOCAL_PROBES / "ozon_zero_human_storage_state.json"

O3_HEADERS = {
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _load_cookie_file(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, dict) and "cookies" in payload:
        payload = payload["cookies"]
    if isinstance(payload, dict):
        cookies = {str(k): str(v) for k, v in payload.items()}
    elif isinstance(payload, list):
        cookies = {
            str(item["name"]): str(item["value"])
            for item in payload
            if isinstance(item, dict) and item.get("name") and item.get("value") is not None
        }
    else:
        raise ValueError("unsupported cookie JSON shape")
    if not cookies:
        raise ValueError("cookie file contains no cookies")
    return cookies, _sha256_bytes(raw)


def _identity(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "query": payload.get("query"),
        "countryCode": payload.get("countryCode"),
        "regionName": payload.get("regionName"),
        "city": payload.get("city"),
        "mobile": payload.get("mobile"),
        "proxy": payload.get("proxy"),
        "hosting": payload.get("hosting"),
    }


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    cleaned = re.sub(r"[^\d,.]", "", str(value)).replace(",", ".")
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return number if number > 0 else None


def _widget_json(value: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_exact_price(payload: dict[str, Any], sku: str) -> dict[str, Any]:
    page_info = payload.get("pageInfo")
    page_url = page_info.get("url") if isinstance(page_info, dict) else None
    if page_url and sku not in str(page_url):
        return {"ok": False, "error": "wrong_product_page", "page_url": str(page_url)}

    states = payload.get("widgetStates")
    if not isinstance(states, dict):
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
                price = _to_number(widget.get("price")) if widget else None
                if price:
                    return {
                        "ok": True,
                        "trusted": True,
                        "state_id": str(state_id),
                        "page_url": page_url,
                        "price": price,
                        "price_card": _to_number(widget.get("cardPrice")),
                        "price_original": _to_number(widget.get("originalPrice")),
                    }

    candidates: list[tuple[str, dict[str, Any], float]] = []
    for key, value in states.items():
        if "webPrice" not in str(key) and "webSale" not in str(key):
            continue
        widget = _widget_json(value)
        price = _to_number(widget.get("price")) if widget else None
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
            "price_card": _to_number(widget.get("cardPrice")),
            "price_original": _to_number(widget.get("originalPrice")),
        }
    if len(candidates) > 1:
        unique = {price for _, _, price in candidates}
        if len(unique) == 1:
            key, widget, price = candidates[0]
            return {
                "ok": True,
                "trusted": False,
                "state_id": key,
                "page_url": page_url,
                "price": price,
                "price_card": _to_number(widget.get("cardPrice")),
                "price_original": _to_number(widget.get("originalPrice")),
            }
        return {
            "ok": False,
            "error": "ambiguous_price_widgets",
            "candidate_count": len(candidates),
            "distinct_prices": sorted(unique),
            "page_url": page_url,
        }
    return {"ok": False, "error": "price_widget_not_found", "page_url": page_url}


def _make_context(label: str) -> ProxyContext:
    print(f"--- {label} ---")
    city = input("City label: ").strip() or label
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    if not proxy or not proxy_user or not proxy_password:
        raise InputValidationError(f"{label}: proxy address, username and password are required")
    return ProxyContext.from_city(
        {"city": city, "proxy": proxy, "proxy_user": proxy_user, "proxy_password": proxy_password},
        require_explicit_scheme=True,
    )


def _run_city(context: ProxyContext, sku: str, cookies: dict[str, str]) -> dict[str, Any]:
    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    identity = _identity(_body_text(neutral.body)) if neutral.ok else None

    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
    response = curl_request_via_proxy(
        context,
        "GET",
        API_URL,
        params={"url": f"/product/{sku}/"},
        headers=headers,
        cookies=cookies,
        impersonate="chrome",
        timeout=45,
        allow_redirects=True,
    )
    text = _body_text(response.body)
    payload: dict[str, Any] | None = None
    parse: dict[str, Any] | None = None
    try:
        decoded = json.loads(text.lstrip("\ufeff \t\r\n"))
        if isinstance(decoded, dict):
            payload = decoded
            parse = _extract_exact_price(decoded, sku)
    except Exception:
        pass
    return {
        "proxy_context": context.safe_identity,
        "neutral": {"transport": neutral.safe_dict(), "identity": identity},
        "entrypoint": {
            "transport": response.safe_dict(),
            "body_chars": len(text),
            "body_sha256": _sha256_text(text),
            "json_decoded": payload is not None,
            "top_level_keys": sorted(payload.keys())[:80] if payload else None,
            "exact_product": parse,
        },
    }


def main() -> int:
    print("=== Ozon proxy-region effect probe C10 ===")
    print("Same anonymous guest cookie state + same SKU. ONLY ProxyContext changes between A and B.")
    print("No Playwright, no login, no PVZ, no browser.")

    cookie_default = str(DEFAULT_COOKIE_FILE)
    cookie_text = input(f"Anonymous Ozon cookie/storage-state file [Enter = {cookie_default}]: ").strip() or cookie_default
    cookie_path = Path(cookie_text)
    if not cookie_path.exists():
        print(f"[ERROR] COOKIE_FILE_NOT_FOUND: {cookie_path}")
        return 11
    try:
        cookies, cookie_sha = _load_cookie_file(cookie_path)
    except Exception as exc:
        print(f"[ERROR] COOKIE_FILE_INVALID: {type(exc).__name__}: {exc}")
        return 12

    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU
    try:
        context_a = _make_context("city A")
        context_b = _make_context("city B")
    except (ProxyContextError, InputValidationError) as exc:
        print(f"[ERROR] SECOND_PROXY_REQUIRED_OR_INVALID: {exc}")
        print("C10 needs two fully specified proxy contexts for two distinct city egresses.")
        return 2

    result_a = _run_city(context_a, sku, cookies)
    result_b = _run_city(context_b, sku, cookies)

    id_a = result_a["neutral"]["identity"]
    id_b = result_b["neutral"]["identity"]
    distinct_egress = bool(
        id_a and id_b and (
            id_a.get("query") != id_b.get("query") or id_a.get("city") != id_b.get("city")
        )
    )
    pa = result_a["entrypoint"]["exact_product"] or {}
    pb = result_b["entrypoint"]["exact_product"] or {}
    status_a = result_a["entrypoint"]["transport"].get("status_code")
    status_b = result_b["entrypoint"]["transport"].get("status_code")

    if not distinct_egress:
        gate = "OZON_PROXY_BINDING_UNPROVEN"
    elif status_a == 400 or status_b == 400:
        gate = "OZON_O3_HEADERS_STALE"
    elif status_a in {401, 403} or status_b in {401, 403}:
        gate = "OZON_GUEST_SESSION_BLOCKED"
    elif pa.get("error") == "ambiguous_price_widgets" or pb.get("error") == "ambiguous_price_widgets":
        gate = "OZON_PRICE_WIDGET_AMBIGUOUS"
    elif not pa.get("ok") or not pb.get("ok"):
        gate = "OZON_PRODUCT_BINDING_UNPROVEN"
    else:
        tuple_a = (pa.get("price"), pa.get("price_card"), pa.get("price_original"))
        tuple_b = (pb.get("price"), pb.get("price_card"), pb.get("price_original"))
        gate = (
            "OZON_PROXY_REGION_EFFECT_PROVEN"
            if tuple_a != tuple_b
            else "OZON_PROXY_REGION_EFFECT_INCONCLUSIVE_SAME_VALUE"
        )

    report = {
        "goal": "prove_ozon_region_effect_from_proxy_with_same_guest_session",
        "sku": sku,
        "cookie_state": {
            "same_for_both_runs": True,
            "sha256": cookie_sha,
            "cookie_count": len(cookies),
            "values_persisted": False,
        },
        "city_a": result_a,
        "city_b": result_b,
        "distinct_proven_egress": distinct_egress,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Cookie values and proxy credentials are not persisted in the report.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate in {"OZON_PROXY_REGION_EFFECT_PROVEN", "OZON_PROXY_REGION_EFFECT_INCONCLUSIVE_SAME_VALUE"} else 8


if __name__ == "__main__":
    raise SystemExit(main())
