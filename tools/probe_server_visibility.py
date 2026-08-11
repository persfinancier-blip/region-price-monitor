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

from curl_transport import request_via_proxy as curl_request
from requests_transport import request_via_proxy as requests_request
from transport import ProxyContext, ProxyContextError, TransportOutcome

NEUTRAL_URL = "https://api.i.pn/json/"
DEFAULT_WB_SKU = "629760017"
DEFAULT_OZON_SKU = "3129447770"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "server_visibility_report.json"

WB_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}
OZON_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "ru-RU,ru;q=0.9,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}


def _body_text(body: str | bytes | None) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256(text: str) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _html_title(text: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title[:200] or None


def _identity(outcome: TransportOutcome) -> dict[str, Any] | None:
    text = _body_text(outcome.body).lstrip("\ufeff \t\r\n")
    try:
        payload = json.loads(text)
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


def _same_egress(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    keys = ("query", "countryCode", "regionName", "city")
    return all(left.get(key) and left.get(key) == right.get(key) for key in keys)


def _save_local(name: str, text: str) -> str | None:
    if not text:
        return None
    path = LOCAL_PROBES / name
    path.write_text(text, encoding="utf-8", errors="replace")
    return str(path)


def _site_evidence(outcome: TransportOutcome, local_name: str) -> dict[str, Any]:
    text = _body_text(outcome.body)
    headers = dict(outcome.headers or {})
    title = _html_title(text)
    low = text.lower()
    evidence = {
        "transport": outcome.safe_dict(),
        "response_received": outcome.status_code is not None,
        "body_chars": len(text),
        "body_sha256": _sha256(text),
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "server_header": headers.get("Server") or headers.get("server"),
        "title": title,
        "antibot_marker": "antibot" in low or "captcha" in low,
        "local_body_file": _save_local(local_name, text),
    }
    return evidence


def main() -> int:
    print("=== Server-only WB/Ozon visibility gate ===")
    print("No Chrome/Selenium/Playwright. No marketplace data endpoints are used.")
    print("Goal: prove that the future server runtime can reach WB and Ozon through ProxyContext.")

    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    wb_sku = input(f"WB SKU [Enter = {DEFAULT_WB_SKU}]: ").strip() or DEFAULT_WB_SKU
    ozon_sku = input(f"Ozon SKU [Enter = {DEFAULT_OZON_SKU}]: ").strip() or DEFAULT_OZON_SKU

    try:
        context = ProxyContext.from_city(
            {
                "city": city,
                "proxy": proxy,
                "proxy_user": proxy_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except ProxyContextError as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    neutral_requests = requests_request(context, "GET", NEUTRAL_URL, timeout=30)
    neutral_curl = curl_request(context, "GET", NEUTRAL_URL, timeout=30, impersonate="chrome")
    requests_identity = _identity(neutral_requests)
    curl_identity = _identity(neutral_curl)
    proxy_ok = (
        neutral_requests.ok
        and neutral_curl.ok
        and _same_egress(requests_identity, curl_identity)
    )

    wb_url = f"https://www.wildberries.ru/catalog/{wb_sku}/detail.aspx"
    ozon_url = f"https://www.ozon.ru/product/{ozon_sku}/"

    wb_outcome = requests_request(
        context,
        "GET",
        wb_url,
        headers=WB_HEADERS,
        timeout=45,
        allow_redirects=True,
    )
    ozon_outcome = curl_request(
        context,
        "GET",
        ozon_url,
        headers=OZON_HEADERS,
        timeout=45,
        impersonate="chrome",
        allow_redirects=True,
    )

    wb = _site_evidence(wb_outcome, "server_visibility_wb.html")
    ozon = _site_evidence(ozon_outcome, "server_visibility_ozon.html")
    wb["requested_url"] = wb_url
    ozon["requested_url"] = ozon_url

    # "Reachable" means the TLS/HTTP client received an HTTP response from the requested HTTPS host.
    # 4xx/antibot is still marketplace reachability evidence; it is not data-access success.
    wb_reachable = bool(wb["response_received"])
    ozon_reachable = bool(ozon["response_received"])
    wb["visibility_gate"] = "WB_SITE_REACHABLE" if wb_reachable else "WB_SITE_UNREACHABLE"
    if ozon_reachable and ozon["antibot_marker"]:
        ozon["visibility_gate"] = "OZON_SITE_REACHABLE_ANTIBOT_RESPONSE"
    elif ozon_reachable:
        ozon["visibility_gate"] = "OZON_SITE_REACHABLE"
    else:
        ozon["visibility_gate"] = "OZON_SITE_UNREACHABLE"

    overall = proxy_ok and wb_reachable and ozon_reachable
    report = {
        "goal": "server_only_marketplace_visibility",
        "proxy_context": context.safe_identity,
        "neutral": {
            "requests": neutral_requests.safe_dict(),
            "curl_cffi": neutral_curl.safe_dict(),
            "requests_identity": requests_identity,
            "curl_cffi_identity": curl_identity,
            "same_egress": _same_egress(requests_identity, curl_identity),
            "gate": "SERVER_PROXY_CONTEXT_CONFIRMED_BOTH_STACKS" if proxy_ok else "SERVER_PROXY_CONTEXT_UNPROVEN",
        },
        "wb": wb,
        "ozon": ozon,
        "overall_gate": "SERVER_SEES_WB_AND_OZON" if overall else "SERVER_MARKETPLACE_VISIBILITY_UNPROVEN",
    }

    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Raw marketplace pages are local/Git-ignored evidence only.")
    return 0 if overall else 5


if __name__ == "__main__":
    raise SystemExit(main())
