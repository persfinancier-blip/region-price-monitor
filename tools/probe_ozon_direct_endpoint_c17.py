from __future__ import annotations

import getpass
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext
from mobile_proxy import find_mobile_proxy, rotate_session
from probe_ozon_reference_entrypoint import (
    API_URL,
    DEFAULT_IMPERSONATE,
    DEFAULT_SKU,
    O3_HEADERS,
    _body_text,
    _is_challenge,
    _parse_exact_price,
)

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_direct_endpoint_c17_report.json"
RAW_DIR = LOCAL_PROBES / "ozon_direct_endpoint_c17"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    print("=== Ozon direct endpoint zero-cookie gate C17 ===")
    print("Find known RU mobile sticky session, then DIRECT entrypoint-api. No cookies/home/browser.")

    proxy_server = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = getpass.getpass("Proxy password: ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        selector = find_mobile_proxy(
            proxy_server=proxy_server,
            proxy_user=proxy_user,
            proxy_password=proxy_password,
            tries=15,
            city_label="ozon-direct",
        )
    except Exception as exc:
        print(f"[ERROR] MOBILE_SELECTOR_FAILED: {type(exc).__name__}: {exc}")
        return 2

    selected = selector.get("selected")
    if not selected:
        report = {
            "goal": "test_direct_ozon_entrypoint_without_cookies_after_mobile_selection",
            "mobile_selector": selector,
            "entrypoint_attempts": [],
            "gate": "OZON_DIRECT_ENDPOINT_MOBILE_SELECTOR_FAILED",
            "credentials_persisted": False,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n=== SAFE REPORT ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {report['gate']}")
        return 8

    rotated_user, _ = rotate_session(proxy_user, str(selected["session_id"]))
    context = ProxyContext.from_city(
        {
            "city": "ozon-direct",
            "proxy": proxy_server,
            "proxy_user": rotated_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )

    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"

    from curl_cffi import requests as creq
    try:
        import curl_cffi
        curl_version = getattr(curl_cffi, "__version__", None)
    except Exception:
        curl_version = None

    attempts: list[dict[str, Any]] = []
    success: dict[str, Any] | None = None

    for strategy in DEFAULT_IMPERSONATE:
        outcome = curl_request_via_proxy(
            context,
            "GET",
            API_URL,
            client=creq,
            params={"url": f"/product/{sku}/"},
            headers=headers,
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
        item = {
            "strategy": strategy,
            "transport": outcome.safe_dict(),
            "body_chars": len(text),
            "json_decoded": payload is not None,
            "challenge_json": challenge,
            "top_level_keys": sorted(payload.keys())[:80] if payload else None,
            "exact_product": parsed,
        }
        attempts.append(item)

        if outcome.status_code == 200 and payload is not None and not challenge and parsed and parsed.get("ok"):
            success = {"strategy": strategy, "result": parsed}
            break

    statuses = [a["transport"].get("status_code") for a in attempts]
    if success:
        gate = "OZON_DIRECT_ENDPOINT_ZERO_COOKIE_DATA_ACCESS_PROVEN"
    elif any(a.get("challenge_json") for a in attempts) or any(s in {401, 403} for s in statuses):
        gate = "OZON_DIRECT_ENDPOINT_ZERO_COOKIE_CHALLENGED"
    elif statuses and all(s == 400 for s in statuses if s is not None):
        gate = "OZON_DIRECT_ENDPOINT_O3_HEADERS_STALE"
    elif any((a.get("exact_product") or {}).get("error") == "wrong_product_page" for a in attempts):
        gate = "OZON_DIRECT_ENDPOINT_PRODUCT_BINDING_FAILED"
    elif any(a.get("json_decoded") for a in attempts):
        gate = "OZON_DIRECT_ENDPOINT_JSON_WITHOUT_PRICE"
    else:
        gate = "OZON_DIRECT_ENDPOINT_TRANSPORT_FAILED"

    report = {
        "goal": "test_direct_ozon_entrypoint_without_cookies_after_mobile_selection",
        "sku": sku,
        "curl_cffi_version": curl_version,
        "mobile_selector": selector,
        "selected_proxy_context": context.safe_identity,
        "zero_cookie_request": True,
        "no_home_warmup": True,
        "no_product_html_request": True,
        "no_browser": True,
        "entrypoint": API_URL,
        "entrypoint_attempts": attempts,
        "success": success,
        "credentials_persisted": False,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] No cookies or proxy credentials are persisted.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate == "OZON_DIRECT_ENDPOINT_ZERO_COOKIE_DATA_ACCESS_PROVEN" else 8


if __name__ == "__main__":
    raise SystemExit(main())
