from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from requests_transport import request_via_proxy
from transport import ProxyContext, ProxyContextError, TransportOutcome

NEUTRAL_URL = "https://api.i.pn/json/"
WB_ENDPOINT = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail"
DEFAULT_WB_SKU = "629760017"
DEFAULT_DIAGNOSTIC_DEST = "-365341"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "wb_current_endpoint_report.json"
RAW_FILE = LOCAL_PROBES / "wb_current_endpoint.json"


def _body_text(body: str | bytes | None) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


def _identity(outcome: TransportOutcome) -> dict[str, Any] | None:
    try:
        payload = json.loads(_body_text(outcome.body).lstrip("\ufeff \t\r\n"))
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


def _find_requested_sku(value: Any, sku: str) -> tuple[bool, list[str] | None]:
    target_int = int(sku) if sku.isdigit() else None
    if isinstance(value, dict):
        for key in ("id", "nm", "nmId", "nmid"):
            current = value.get(key)
            if current == sku or (target_int is not None and current == target_int):
                return True, sorted(str(k) for k in value.keys())[:80]
        for nested in value.values():
            found, keys = _find_requested_sku(nested, sku)
            if found:
                return True, keys
    elif isinstance(value, list):
        for nested in value:
            found, keys = _find_requested_sku(nested, sku)
            if found:
                return True, keys
    return False, None


def main() -> int:
    print("=== WB current internal endpoint probe ===")
    print("Server-only: Requests + ProxyContext. No Chrome and no captured browser cookies/tokens.")

    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    sku = input(f"WB SKU [Enter = {DEFAULT_WB_SKU}]: ").strip() or DEFAULT_WB_SKU
    dest = input(f"WB diagnostic dest [Enter = owner capture {DEFAULT_DIAGNOSTIC_DEST}]: ").strip() or DEFAULT_DIAGNOSTIC_DEST

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

    neutral = request_via_proxy(context, "GET", NEUTRAL_URL, timeout=30)
    identity = _identity(neutral)
    proxy_ok = bool(neutral.ok and identity and identity.get("query") and identity.get("city"))

    params = {
        "appType": "1",
        "curr": "rub",
        "dest": dest,
        "spp": "30",
        "hide_vflags": "4294967296",
        "hide_dtype": "15",
        "mtype": "257",
        "lang": "ru",
        "ab_testing": "false",
        "nm": sku,
    }
    referer = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
    headers = {
        "accept": "*/*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "referer": referer,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
        ),
        "x-requested-with": "XMLHttpRequest",
        "x-spa-version": "14.20.4",
    }

    outcome = request_via_proxy(
        context,
        "GET",
        WB_ENDPOINT,
        params=params,
        headers=headers,
        timeout=45,
        allow_redirects=True,
    )
    text = _body_text(outcome.body)
    if text:
        RAW_FILE.write_text(text, encoding="utf-8", errors="replace")

    payload: Any = None
    json_ok = False
    top_level_keys: list[str] | None = None
    requested_sku_found = False
    matched_object_keys: list[str] | None = None
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
        json_ok = True
        if isinstance(payload, dict):
            top_level_keys = sorted(str(k) for k in payload.keys())[:80]
        requested_sku_found, matched_object_keys = _find_requested_sku(payload, sku)
    except Exception:
        pass

    headers_out = dict(outcome.headers or {})
    if not proxy_ok:
        gate = "WB_PROXY_CONTEXT_UNPROVEN"
    elif json_ok and requested_sku_found:
        gate = "WB_CURRENT_ENDPOINT_DATA_ACCESS_PROVEN"
    elif outcome.status_code in {403, 429, 498} or (headers_out.get("server") or headers_out.get("Server")) == "wbaas":
        gate = "WB_CURRENT_ENDPOINT_REACHABLE_BUT_BLOCKED"
    elif json_ok:
        gate = "WB_CURRENT_ENDPOINT_JSON_WITHOUT_REQUESTED_SKU"
    elif outcome.status_code is not None:
        gate = "WB_CURRENT_ENDPOINT_NON_JSON"
    else:
        gate = "WB_CURRENT_ENDPOINT_TRANSPORT_FAILED"

    report = {
        "goal": "wb_current_internal_endpoint_access",
        "proxy_context": context.safe_identity,
        "neutral": {
            "transport": neutral.safe_dict(),
            "identity": identity,
            "gate": "WB_PROXY_CONTEXT_CONFIRMED" if proxy_ok else "WB_PROXY_CONTEXT_UNPROVEN",
        },
        "request": {
            "endpoint": WB_ENDPOINT,
            "sku": sku,
            "diagnostic_dest": dest,
            "source": "owner_current_devtools_capture_2026-08-11",
            "captured_browser_secrets_supplied": False,
        },
        "response": {
            "transport": outcome.safe_dict(),
            "content_type": headers_out.get("Content-Type") or headers_out.get("content-type"),
            "server_header": headers_out.get("Server") or headers_out.get("server"),
            "body_chars": len(text),
            "body_sha256": _sha256(text),
            "json_decoded": json_ok,
            "top_level_keys": top_level_keys,
            "requested_sku_found": requested_sku_found,
            "matched_object_keys": matched_object_keys,
            "local_body_file": str(RAW_FILE) if text else None,
        },
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Raw WB body is local/Git-ignored. Captured browser cookies/tokens are not used.")
    return 0 if gate == "WB_CURRENT_ENDPOINT_DATA_ACCESS_PROVEN" else 6


if __name__ == "__main__":
    raise SystemExit(main())
