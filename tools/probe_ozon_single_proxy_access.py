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
API_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
DEFAULT_SKU = "3129447770"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_single_proxy_access_report.json"
RAW_PAGE_FILE = LOCAL_PROBES / "ozon_single_proxy_product.html"
RAW_API_FILE = LOCAL_PROBES / "ozon_single_proxy_entrypoint.json"
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

DENIAL_MARKERS = (
    "похоже, нет соединения",
    "выключите vpn",
    "antibot captcha",
    "captcha",
    "капча",
    "доступ ограничен",
)


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256_text(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


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
    return cookies, hashlib.sha256(raw).hexdigest()


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


def _denial_marker(title: str, body: str) -> bool:
    sample = f"{title}\n{body[:12000]}".lower()
    return any(marker in sample for marker in DENIAL_MARKERS)


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
    print("=== Ozon single-proxy access gate C11 ===")
    print("FIRST prove one proxy can load Ozon and the entrypoint for one SKU.")
    print("No second city. No regional comparison. No Playwright/Selenium/login/PVZ.")

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
        context = _make_context()
    except (ProxyContextError, InputValidationError) as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    neutral_text = _body_text(neutral.body)
    identity = _identity(neutral_text) if neutral.ok else None

    product_url = f"https://www.ozon.ru/product/{sku}/"
    page = curl_request_via_proxy(
        context,
        "GET",
        product_url,
        cookies=cookies,
        impersonate="chrome",
        timeout=45,
        allow_redirects=True,
    )
    page_text = _body_text(page.body)
    if page_text:
        RAW_PAGE_FILE.write_text(page_text, encoding="utf-8", errors="replace")
    page_title = _title(page_text)
    page_denied = _denial_marker(page_title, page_text)

    headers = dict(O3_HEADERS)
    headers["Referer"] = product_url
    api = curl_request_via_proxy(
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
    api_text = _body_text(api.body)
    if api_text:
        RAW_API_FILE.write_text(api_text, encoding="utf-8", errors="replace")

    payload: dict[str, Any] | None = None
    page_info_url: str | None = None
    try:
        decoded = json.loads(api_text.lstrip("\ufeff \t\r\n"))
        if isinstance(decoded, dict):
            payload = decoded
            page_info = decoded.get("pageInfo")
            if isinstance(page_info, dict) and page_info.get("url") is not None:
                page_info_url = str(page_info.get("url"))
    except Exception:
        pass

    exact_sku_bound = payload is not None and (not page_info_url or sku in page_info_url)
    api_denied = _denial_marker("", api_text)

    if not neutral.ok or identity is None:
        gate = "OZON_SINGLE_PROXY_TRANSPORT_FAILED"
    elif api.status_code == 400:
        gate = "OZON_SINGLE_PROXY_O3_HEADERS_STALE"
    elif api.status_code in {401, 403} or page.status_code in {401, 403} or api_denied or page_denied:
        gate = "OZON_SINGLE_PROXY_GUEST_SESSION_BLOCKED"
    elif api.status_code == 200 and payload is not None and exact_sku_bound:
        gate = "OZON_SINGLE_PROXY_ENTRYPOINT_DATA_ACCESS_PROVEN"
    elif api.status_code == 200 and payload is not None and not exact_sku_bound:
        gate = "OZON_SINGLE_PROXY_PRODUCT_BINDING_UNPROVEN"
    elif page.status_code == 200 and not page_denied:
        gate = "OZON_SINGLE_PROXY_PRODUCT_PAGE_LOADED_ONLY"
    else:
        gate = "OZON_SINGLE_PROXY_GUEST_SESSION_BLOCKED"

    report = {
        "goal": "prove_single_proxy_ozon_access_before_region_work",
        "sku": sku,
        "proxy_context": context.safe_identity,
        "cookie_state": {
            "sha256": cookie_sha,
            "cookie_count": len(cookies),
            "values_persisted": False,
        },
        "neutral": {"transport": neutral.safe_dict(), "identity": identity},
        "product_page": {
            "url": product_url,
            "transport": page.safe_dict(),
            "title": page_title,
            "denial_marker": page_denied,
            "body_chars": len(page_text),
            "body_sha256": _sha256_text(page_text),
            "local_body_file": str(RAW_PAGE_FILE) if page_text else None,
        },
        "entrypoint": {
            "url": API_URL,
            "transport": api.safe_dict(),
            "json_decoded": payload is not None,
            "top_level_keys": sorted(payload.keys())[:80] if payload else None,
            "page_info_url": page_info_url,
            "requested_sku_bound": exact_sku_bound,
            "denial_marker": api_denied,
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
    print("[INFO] Raw bodies are local/Git-ignored; cookie values and proxy credentials are not persisted in SAFE REPORT.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate == "OZON_SINGLE_PROXY_ENTRYPOINT_DATA_ACCESS_PROVEN" else 8


if __name__ == "__main__":
    raise SystemExit(main())
