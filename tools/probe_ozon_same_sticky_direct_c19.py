from __future__ import annotations

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
from mobile_proxy import _parse_combined_proxy, _transport_auth_failed, rotate_session
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
C18_REPORT = LOCAL_PROBES / "ozon_mobile_proxy_selector_report.json"
REPORT_FILE = LOCAL_PROBES / "ozon_same_sticky_direct_c19_report.json"
RAW_DIR = LOCAL_PROBES / "ozon_same_sticky_direct_c19"
RAW_DIR.mkdir(parents=True, exist_ok=True)
NEUTRAL_URL = "https://api.i.pn/json/"


def _decode_json(body: Any) -> dict[str, Any] | None:
    text = _body_text(body)
    try:
        value = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _load_c18_selection() -> tuple[str, str, dict[str, Any]]:
    if not C18_REPORT.exists():
        raise ValueError(f"C18 SAFE report not found: {C18_REPORT}")
    data = json.loads(C18_REPORT.read_text(encoding="utf-8"))
    if data.get("gate") != "OZON_STICKY_MOBILE_OPERATOR_SELECTED":
        raise ValueError(f"C18 gate is not accepted: {data.get('gate')}")
    selected = data.get("selected") or {}
    session_id = str(selected.get("session_id") or "").strip()
    identity = selected.get("identity") or {}
    selected_ip = str(identity.get("query") or "").strip()
    if not session_id or not selected_ip:
        raise ValueError("C18 selected session_id/public IP missing")
    return session_id, selected_ip, data


def main() -> int:
    print("=== Ozon SAME sticky-session direct endpoint gate C19 ===")
    print("Reuse exact C18 sticky session -> verify same IP -> DIRECT entrypoint-api.")
    print("ZERO cookies. NO Ozon home. NO product HTML. NO browser.")
    print("Proxy input is VISIBLE; credentials are NOT saved.")

    try:
        c18_session_id, c18_ip, c18 = _load_c18_selection()
    except Exception as exc:
        report = {
            "goal": "reuse_exact_c18_sticky_session_for_direct_ozon_entrypoint",
            "gate": "OZON_SAME_STICKY_C18_REPORT_INVALID",
            "error": f"{type(exc).__name__}: {exc}",
            "credentials_persisted": False,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {report['gate']}")
        return 8

    print(f"C18 selected session: {c18_session_id}")
    print(f"C18 selected public IP: {c18_ip}")
    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
        exact_user, exact_sid = rotate_session(proxy_user, c18_session_id)
        if exact_sid != c18_session_id:
            raise ValueError("exact sticky session id was not preserved")
        context = ProxyContext.from_city(
            {
                "city": "ozon-same-sticky",
                "proxy": proxy_server,
                "proxy_user": exact_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except Exception as exc:
        report = {
            "goal": "reuse_exact_c18_sticky_session_for_direct_ozon_entrypoint",
            "c18_session_id": c18_session_id,
            "c18_selected_ip": c18_ip,
            "gate": "OZON_SAME_STICKY_TRANSPORT_FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "credentials_persisted": False,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {report['gate']}")
        return 8

    print("[1/2] Verifying exact sticky session still has the C18 public IP ...", flush=True)
    neutral = curl_request_via_proxy(
        context,
        "GET",
        NEUTRAL_URL,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True,
    )
    neutral_transport = neutral.safe_dict()
    neutral_payload = _decode_json(neutral.body) if neutral.ok else None
    neutral_ip = str((neutral_payload or {}).get("query") or "").strip() or None

    if _transport_auth_failed(neutral_transport):
        gate = "OZON_SAME_STICKY_PROXY_AUTH_FAILED"
        report = {
            "goal": "reuse_exact_c18_sticky_session_for_direct_ozon_entrypoint",
            "sku": sku,
            "c18_session_id": c18_session_id,
            "c18_selected_ip": c18_ip,
            "same_sticky_neutral": {
                "transport": neutral_transport,
                "observed_ip": neutral_ip,
            },
            "entrypoint_attempts": [],
            "credentials_persisted": False,
            "gate": gate,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n=== SAFE REPORT ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {gate}")
        return 8

    if not neutral.ok or neutral_payload is None:
        gate = "OZON_SAME_STICKY_TRANSPORT_FAILED"
    elif neutral_ip != c18_ip:
        gate = "OZON_SAME_STICKY_IDENTITY_MISMATCH"
    else:
        gate = None

    if gate:
        report = {
            "goal": "reuse_exact_c18_sticky_session_for_direct_ozon_entrypoint",
            "sku": sku,
            "c18_session_id": c18_session_id,
            "c18_selected_ip": c18_ip,
            "same_sticky_neutral": {
                "transport": neutral_transport,
                "observed_ip": neutral_ip,
                "same_ip": neutral_ip == c18_ip,
            },
            "entrypoint_attempts": [],
            "credentials_persisted": False,
            "gate": gate,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n=== SAFE REPORT ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {gate}")
        return 8

    print(f"    SAME IP CONFIRMED: {neutral_ip}")
    print("[2/2] Calling Ozon entrypoint directly with ZERO cookies ...", flush=True)

    from curl_cffi import requests as creq
    try:
        import curl_cffi
        curl_version = getattr(curl_cffi, "__version__", None)
    except Exception:
        curl_version = None

    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
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
        payload = _decode_json(outcome.body)
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
        print(
            f"    [{strategy}] status={outcome.status_code} json={payload is not None} "
            f"challenge={challenge} parsed_ok={bool(parsed and parsed.get('ok'))}",
            flush=True,
        )
        if outcome.status_code == 200 and payload is not None and not challenge and parsed and parsed.get("ok"):
            success = {"strategy": strategy, "result": parsed}
            break

    statuses = [a["transport"].get("status_code") for a in attempts]
    if success:
        gate = "OZON_SAME_STICKY_DIRECT_ENDPOINT_ZERO_COOKIE_DATA_ACCESS_PROVEN"
    elif any(a.get("challenge_json") for a in attempts) or any(s in {401, 403} for s in statuses):
        gate = "OZON_SAME_STICKY_DIRECT_ENDPOINT_CHALLENGED"
    elif statuses and all(s == 400 for s in statuses if s is not None):
        gate = "OZON_SAME_STICKY_O3_HEADERS_STALE"
    elif any((a.get("exact_product") or {}).get("error") == "wrong_product_page" for a in attempts):
        gate = "OZON_SAME_STICKY_PRODUCT_BINDING_FAILED"
    elif any(a.get("json_decoded") for a in attempts):
        gate = "OZON_SAME_STICKY_JSON_WITHOUT_PRICE"
    else:
        gate = "OZON_SAME_STICKY_TRANSPORT_FAILED"

    report = {
        "goal": "reuse_exact_c18_sticky_session_for_direct_ozon_entrypoint",
        "sku": sku,
        "curl_cffi_version": curl_version,
        "c18_session_id": c18_session_id,
        "c18_selected_ip": c18_ip,
        "c18_operator": (c18.get("selected") or {}).get("operator"),
        "selected_proxy_context": context.safe_identity,
        "same_sticky_neutral": {
            "transport": neutral_transport,
            "observed_ip": neutral_ip,
            "same_ip": neutral_ip == c18_ip,
        },
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
    return 0 if gate == "OZON_SAME_STICKY_DIRECT_ENDPOINT_ZERO_COOKIE_DATA_ACCESS_PROVEN" else 8


if __name__ == "__main__":
    raise SystemExit(main())
