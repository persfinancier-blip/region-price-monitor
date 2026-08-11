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
DEFAULT_IMPERSONATE = ("chrome", "chrome146", "chrome145", "chrome142", "chrome136")
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_reference_entrypoint_report.json"
RAW_DIR = LOCAL_PROBES / "ozon_reference_entrypoint"
RAW_DIR.mkdir(parents=True, exist_ok=True)

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

CHALLENGE_KEYS = {"blockURL", "challengeURL", "incidentId", "supportURL", "timeoutSec"}


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


def _load_cookies(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if isinstance(data, dict):
        cookies = {str(k): str(v) for k, v in data.items()}
    elif isinstance(data, list):
        cookies = {
            str(item["name"]): str(item["value"])
            for item in data
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


def _is_challenge(payload: dict[str, Any]) -> bool:
    return bool(CHALLENGE_KEYS.intersection(payload.keys())) and "widgetStates" not in payload


def _parse_exact_price(payload: dict[str, Any], sku: str) -> dict[str, Any]:
    if _is_challenge(payload):
        return {"ok": False, "error": "challenge_json"}

    page_info = payload.get("pageInfo")
    page_url = page_info.get("url") if isinstance(page_info, dict) else None
    if page_url and sku not in str(page_url):
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
        unique_prices = {price for _, _, price in candidates}
        if len(unique_prices) == 1:
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
            "distinct_prices": sorted(unique_prices),
            "page_url": page_url,
        }
    return {"ok": False, "error": "price_widget_not_found", "page_url": page_url}


def _make_context() -> ProxyContext:
    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    if not proxy or not proxy_user or not proxy_password:
        raise InputValidationError("proxy address, username and password are required")
    return ProxyContext.from_city(
        {"city": city, "proxy": proxy, "proxy_user": proxy_user, "proxy_password": proxy_password},
        require_explicit_scheme=True,
    )


def main() -> int:
    print("=== Ozon recovered-reference direct entrypoint probe C15 ===")
    print("ONE guest cookie file + ONE ProxyContext + ONE SKU -> DIRECT entrypoint-api.")
    print("No Ozon home warmup. No product HTML. No browser. No login/PVZ/region comparison.")

    cookie_text = input("Anonymous/guest Ozon cookies JSON path: ").strip()
    if not cookie_text:
        print("[ERROR] COOKIE_FILE_REQUIRED")
        return 11
    cookie_path = Path(cookie_text)
    if not cookie_path.exists():
        print(f"[ERROR] COOKIE_FILE_NOT_FOUND: {cookie_path}")
        return 11
    try:
        cookies, cookie_sha = _load_cookies(cookie_path)
    except Exception as exc:
        print(f"[ERROR] COOKIE_FILE_INVALID: {type(exc).__name__}: {exc}")
        return 12

    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU
    try:
        context = _make_context()
    except (ProxyContextError, InputValidationError) as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    neutral_text = _body_text(neutral.body)
    identity = _identity(neutral_text) if neutral.ok else None

    from curl_cffi import requests as creq

    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
    attempts: list[dict[str, Any]] = []
    success_parse: dict[str, Any] | None = None
    success_strategy: str | None = None
    successful_payload = False

    for strategy in DEFAULT_IMPERSONATE:
        outcome = curl_request_via_proxy(
            context,
            "GET",
            API_URL,
            client=creq,
            params={"url": f"/product/{sku}/"},
            headers=headers,
            cookies=cookies,
            impersonate=strategy,
            timeout=45,
            allow_redirects=True,
        )
        text = _body_text(outcome.body)
        if text:
            (RAW_DIR / f"{strategy}.txt").write_text(text[:250_000], encoding="utf-8", errors="replace")
        payload: dict[str, Any] | None = None
        try:
            decoded = json.loads(text.lstrip("\ufeff \t\r\n"))
            if isinstance(decoded, dict):
                payload = decoded
        except Exception:
            pass
        challenge = bool(payload and _is_challenge(payload))
        parsed = _parse_exact_price(payload, sku) if payload is not None else None
        attempts.append(
            {
                "strategy": strategy,
                "transport": outcome.safe_dict(),
                "body_chars": len(text),
                "body_sha256": _sha256_text(text),
                "json_decoded": payload is not None,
                "challenge_json": challenge,
                "top_level_keys": sorted(payload.keys())[:80] if payload else None,
                "exact_product": parsed,
            }
        )
        if outcome.status_code == 200 and payload is not None and not challenge:
            successful_payload = True
            if parsed and parsed.get("ok"):
                success_parse = parsed
                success_strategy = strategy
                break
            if parsed and parsed.get("error") in {"wrong_product_page", "ambiguous_price_widgets"}:
                break

    statuses = [a["transport"].get("status_code") for a in attempts]
    parses = [a.get("exact_product") or {} for a in attempts]
    if not neutral.ok or identity is None:
        gate = "OZON_REFERENCE_TRANSPORT_FAILED"
    elif success_parse is not None:
        gate = "OZON_REFERENCE_ENTRYPOINT_DATA_ACCESS_PROVEN"
    elif any(p.get("error") == "wrong_product_page" for p in parses):
        gate = "OZON_REFERENCE_PRODUCT_BINDING_FAILED"
    elif any(p.get("error") == "ambiguous_price_widgets" for p in parses):
        gate = "OZON_REFERENCE_PRICE_AMBIGUOUS"
    elif successful_payload:
        gate = "OZON_REFERENCE_PRICE_NOT_FOUND"
    elif statuses and all(s == 400 for s in statuses if s is not None):
        gate = "OZON_REFERENCE_O3_HEADERS_STALE"
    elif any(s in {401, 403} for s in statuses) or any(a.get("challenge_json") for a in attempts):
        gate = "OZON_REFERENCE_COOKIES_REJECTED"
    else:
        gate = "OZON_REFERENCE_TRANSPORT_FAILED"

    report = {
        "goal": "reproduce_recovered_ozon_reference_reader_without_invented_warmup",
        "sku": sku,
        "proxy_context": context.safe_identity,
        "neutral": {"transport": neutral.safe_dict(), "identity": identity},
        "cookie_state": {
            "sha256": cookie_sha,
            "cookie_count": len(cookies),
            "cookie_names": sorted(cookies.keys()),
            "values_persisted": False,
        },
        "entrypoint": API_URL,
        "no_home_warmup": True,
        "no_product_html_request": True,
        "attempts": attempts,
        "success_strategy": success_strategy,
        "result": success_parse,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Raw response bodies are local/Git-ignored. Cookie values and proxy credentials are not persisted.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate == "OZON_REFERENCE_ENTRYPOINT_DATA_ACCESS_PROVEN" else 8


if __name__ == "__main__":
    raise SystemExit(main())
