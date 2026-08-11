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

NEUTRAL_URL = "https://api.i.pn/json/"
OZON_HOME = "https://www.ozon.ru/"
API_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
DEFAULT_SKU = "3129447770"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_curl_guest_bootstrap_report.json"
RAW_HOME_FILE = LOCAL_PROBES / "ozon_curl_guest_home.html"
RAW_PRODUCT_FILE = LOCAL_PROBES / "ozon_curl_guest_product.html"
RAW_API_FILE = LOCAL_PROBES / "ozon_curl_guest_entrypoint.json"

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

DENIAL_MARKERS = (
    "похоже, нет соединения",
    "выключите vpn",
    "antibot captcha",
    "captcha",
    "капча",
    "доступ ограничен",
)
CHALLENGE_KEYS = {"challengeURL", "blockURL", "incidentId"}


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256_text(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


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


def _title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:200]


def _denied_html(title: str, body: str) -> bool:
    sample = f"{title}\n{body[:12000]}".lower()
    return any(marker in sample for marker in DENIAL_MARKERS)


def _decode_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _challenge_json(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    return bool(CHALLENGE_KEYS.intersection(payload.keys()))


def _cookie_names(session: Any) -> list[str]:
    cookies = getattr(session, "cookies", None)
    if cookies is None:
        return []
    try:
        return sorted({str(name) for name in cookies.keys()})
    except Exception:
        pass
    names: set[str] = set()
    jar = getattr(cookies, "jar", None)
    if jar is not None:
        try:
            for cookie in jar:
                name = getattr(cookie, "name", None)
                if name:
                    names.add(str(name))
        except Exception:
            pass
    return sorted(names)


def _make_context() -> ProxyContext:
    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    if not proxy or not proxy_user or not proxy_password:
        raise InputValidationError("single proxy address, username and password are required")
    return ProxyContext.from_city(
        {"city": city, "proxy": proxy, "proxy_user": proxy_user, "proxy_password": proxy_password},
        require_explicit_scheme=True,
    )


def main() -> int:
    print("=== Ozon autonomous curl guest bootstrap C12 ===")
    print("Empty curl_cffi Session -> Ozon home -> product -> entrypoint through ONE ProxyContext.")
    print("No cookie file. No browser. No login. No PVZ. No region comparison.")

    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU
    try:
        context = _make_context()
    except (ProxyContextError, InputValidationError) as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    neutral_text = _body_text(neutral.body)
    identity = _identity(neutral_text) if neutral.ok else None

    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("[ERROR] CURL_CFFI_NOT_INSTALLED")
        return 10

    session = creq.Session(impersonate="chrome")

    home = curl_request_via_proxy(
        context,
        "GET",
        OZON_HOME,
        session=session,
        timeout=45,
        allow_redirects=True,
    )
    home_text = _body_text(home.body)
    if home_text:
        RAW_HOME_FILE.write_text(home_text, encoding="utf-8", errors="replace")
    home_title = _title(home_text)
    home_denied = _denied_html(home_title, home_text)
    cookies_after_home = _cookie_names(session)

    product_url = f"https://www.ozon.ru/product/{sku}/"
    product = curl_request_via_proxy(
        context,
        "GET",
        product_url,
        session=session,
        timeout=45,
        allow_redirects=True,
    )
    product_text = _body_text(product.body)
    if product_text:
        RAW_PRODUCT_FILE.write_text(product_text, encoding="utf-8", errors="replace")
    product_title = _title(product_text)
    product_denied = _denied_html(product_title, product_text)
    cookies_after_product = _cookie_names(session)

    headers = dict(O3_HEADERS)
    headers["Referer"] = product_url
    api = curl_request_via_proxy(
        context,
        "GET",
        API_URL,
        session=session,
        params={"url": f"/product/{sku}/"},
        headers=headers,
        timeout=45,
        allow_redirects=True,
    )
    api_text = _body_text(api.body)
    if api_text:
        RAW_API_FILE.write_text(api_text, encoding="utf-8", errors="replace")
    payload = _decode_json(api_text)
    challenged_api = _challenge_json(payload)
    page_info_url: str | None = None
    if payload is not None:
        page_info = payload.get("pageInfo")
        if isinstance(page_info, dict) and page_info.get("url") is not None:
            page_info_url = str(page_info.get("url"))
    exact_sku_bound = bool(
        api.status_code == 200
        and payload is not None
        and not challenged_api
        and (page_info_url is None or sku in page_info_url)
    )
    cookies_after_api = _cookie_names(session)

    if not neutral.ok or identity is None:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_TRANSPORT_FAILED"
    elif home.status_code in {401, 403} or home_denied:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_CHALLENGED_AT_HOME"
    elif product.status_code in {401, 403} or product_denied:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_CHALLENGED_AT_PRODUCT"
    elif api.status_code == 400:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_O3_HEADERS_STALE"
    elif api.status_code in {401, 403} or challenged_api:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_CHALLENGED_AT_ENTRYPOINT"
    elif api.status_code == 200 and payload is not None and exact_sku_bound:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_AND_ENTRYPOINT_PROVEN"
    elif api.status_code == 200 and payload is not None:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_PRODUCT_BINDING_UNPROVEN"
    else:
        gate = "OZON_CURL_GUEST_BOOTSTRAP_CHALLENGED_AT_ENTRYPOINT"

    report = {
        "goal": "prove_autonomous_empty_curl_session_bootstrap_for_one_ozon_proxy",
        "sku": sku,
        "proxy_context": context.safe_identity,
        "neutral": {"transport": neutral.safe_dict(), "identity": identity},
        "guest_session": {
            "initial_cookie_count": 0,
            "cookie_names_after_home": cookies_after_home,
            "cookie_count_after_home": len(cookies_after_home),
            "cookie_names_after_product": cookies_after_product,
            "cookie_count_after_product": len(cookies_after_product),
            "cookie_names_after_entrypoint": cookies_after_api,
            "cookie_count_after_entrypoint": len(cookies_after_api),
            "cookie_values_persisted": False,
        },
        "home": {
            "transport": home.safe_dict(),
            "title": home_title,
            "denial_marker": home_denied,
            "body_chars": len(home_text),
            "body_sha256": _sha256_text(home_text),
            "local_body_file": str(RAW_HOME_FILE) if home_text else None,
        },
        "product": {
            "url": product_url,
            "transport": product.safe_dict(),
            "title": product_title,
            "denial_marker": product_denied,
            "body_chars": len(product_text),
            "body_sha256": _sha256_text(product_text),
            "local_body_file": str(RAW_PRODUCT_FILE) if product_text else None,
        },
        "entrypoint": {
            "url": API_URL,
            "transport": api.safe_dict(),
            "json_decoded": payload is not None,
            "challenge_json": challenged_api,
            "top_level_keys": sorted(payload.keys())[:80] if payload else None,
            "page_info_url": page_info_url,
            "requested_sku_bound": exact_sku_bound,
            "body_chars": len(api_text),
            "body_sha256": _sha256_text(api_text),
            "local_body_file": str(RAW_API_FILE) if api_text else None,
        },
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Only cookie names/count are reported. Cookie values and proxy credentials are not persisted.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate == "OZON_CURL_GUEST_BOOTSTRAP_AND_ENTRYPOINT_PROVEN" else 8


if __name__ == "__main__":
    raise SystemExit(main())
