from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for p in (CORE, TOOLS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from curl_transport import request_via_proxy as curl_request_via_proxy
from mobile_proxy import _decode_json, _parse_combined_proxy, rotate_session
from transport import ProxyContext

LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
PROFILE_ROOT = CORE / "local" / "profiles" / "ozon_c37_persistent"
OZON_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
IP_URL = "https://api.i.pn/json/"
READY_COOKIE = "__Secure-ext_xcid"
UI_CHALLENGE_MARKERS = (
    "captcha",
    "antibot",
    "доступ ограничен",
    "проверка безопасности",
    "challenge",
)


def _load_proxy(cli_proxy: str | None) -> str:
    if cli_proxy and cli_proxy.strip():
        return cli_proxy.strip()
    if LOCAL_PROXY_FILE.exists():
        value = LOCAL_PROXY_FILE.read_text(encoding="utf-8").strip()
        if value:
            print(f"[INFO] Using cached proxy: {LOCAL_PROXY_FILE}")
            return value
    raise ValueError(f"cached proxy not found: {LOCAL_PROXY_FILE}")


def _fresh_context(raw_proxy: str) -> tuple[ProxyContext, str]:
    proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
    bound_user, session_id = rotate_session(proxy_user)
    context = ProxyContext.from_city(
        {
            "city": "ozon-c37-persistent-profile",
            "proxy": proxy_server,
            "proxy_user": bound_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )
    return context, session_id


def _proxy_dict(context: ProxyContext) -> dict[str, str]:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return {
        "server": f"{context.scheme}://{host}:{context.port}",
        "username": context.proxy_user,
        "password": context.proxy_password,
    }


def _neutral_ip(context: ProxyContext) -> str | None:
    outcome = curl_request_via_proxy(
        context,
        "GET",
        IP_URL,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True,
    )
    payload = _decode_json(outcome.body) if outcome.ok else None
    return str((payload or {}).get("query") or "").strip() or None


def _security_details(response: Any) -> dict[str, Any]:
    getter = getattr(response, "security_details", None) if response is not None else None
    if not callable(getter):
        return {}
    try:
        value = getter()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _observe(context: Any, run_no: int) -> dict[str, Any]:
    page = context.new_page()
    try:
        response = page.goto(OZON_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        try:
            body = (page.text_content("body") or "")[:12000].lower()
        except Exception:
            body = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        cookies = list(context.cookies())
        names = sorted({str(c.get("name") or "") for c in cookies if c.get("name")})
        state = page.evaluate(
            """() => ({href: location.href, protocol: location.protocol, secureContext: window.isSecureContext, ua: navigator.userAgent})"""
        )
        details = _security_details(response)
        result = {
            "run": run_no,
            "status": int(response.status) if response is not None else None,
            "final_url": str((state or {}).get("href") or page.url or ""),
            "secure_context": bool((state or {}).get("secureContext")),
            "user_agent": str((state or {}).get("ua") or ""),
            "cookie_count": len(cookies),
            "cookie_names": names,
            "ext_xcid": READY_COOKIE in names,
            "challenge": any(marker in body or marker in title for marker in UI_CHALLENGE_MARKERS),
            "tls_protocol": details.get("protocol"),
            "cert_subject": details.get("subjectName"),
            "cert_issuer": details.get("issuer"),
        }
        print(
            f"      run={run_no} status={result['status']} cookies={len(cookies)} unique={len(names)} "
            f"ext_xcid={result['ext_xcid']} challenge={result['challenge']} secure={result['secure_context']}"
        )
        print(f"      run={run_no} cookie_names={','.join(names)}")
        print(f"      run={run_no} user_agent={result['user_agent'][:120]}")
        if result["tls_protocol"]:
            print(
                f"      run={run_no} tls={result['tls_protocol']} "
                f"subject={result['cert_subject']} issuer={result['cert_issuer']}"
            )
        return result
    finally:
        page.close()


def _material(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("status"),
        bool(item.get("challenge")),
        bool(item.get("ext_xcid")),
        item.get("cookie_count"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="C37: persistent stock Firefox profile on one sticky mobile proxy")
    parser.add_argument("--proxy")
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    if args.runs < 2 or args.runs > 5:
        print("[ERROR] runs must be 2..5")
        return 2

    print("=== Ozon persistent Firefox profile C37 ===")
    print("ONE sticky/IP. ONE persistent Firefox profile reused across sequential launches.")
    print("Observation only: no CAPTCHA interaction/submission and no fingerprint tuning.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        proxy_context, session_id = _fresh_context(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] C37_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    selected_ip = _neutral_ip(proxy_context)
    print(f"[1/{args.runs + 1}] sticky_session={session_id} selected_ip={selected_ip or 'UNPROVEN'}")
    if not selected_ip:
        print("[EVIDENCE] OZON_C37_STICKY_IP_UNPROVEN")
        return 8

    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    profile_dir = PROFILE_ROOT / session_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"      persistent_profile={profile_dir}")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[ERROR] PLAYWRIGHT_IMPORT_FAILED: {type(exc).__name__}: {exc}")
        return 8

    results: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        for run_no in range(1, args.runs + 1):
            print(f"[{run_no + 1}/{args.runs + 1}] Persistent Firefox launch #{run_no} ...")
            try:
                context = pw.firefox.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=not args.visible,
                    proxy=_proxy_dict(proxy_context),
                    locale="ru-RU",
                )
                try:
                    item = _observe(context, run_no)
                    results.append(item)
                finally:
                    context.close()
            except Exception as exc:
                print(f"      browser_error={type(exc).__name__}: {proxy_context.redact(str(exc))}")
                print("[EVIDENCE] OZON_C37_PERSISTENT_PROFILE_BROWSER_FAILED")
                return 8

            current_ip = _neutral_ip(proxy_context)
            print(f"      after_run{run_no}_ip={current_ip}")
            if current_ip != selected_ip:
                print("[EVIDENCE] OZON_C37_STICKY_IP_DRIFT")
                return 8
            if run_no < args.runs:
                time.sleep(2)

    print("\n=== C37 SUMMARY ===")
    for item in results:
        print(
            f"run={item['run']} status={item.get('status')} cookies={item.get('cookie_count')} "
            f"ext_xcid={item.get('ext_xcid')} challenge={item.get('challenge')} secure={item.get('secure_context')}"
        )

    first = results[0]
    improved = any(
        item.get("ext_xcid")
        or (item.get("cookie_count") or 0) > (first.get("cookie_count") or 0)
        or _material(item) != _material(first)
        for item in results[1:]
    )
    if improved:
        print("[EVIDENCE] OZON_C37_PERSISTENT_PROFILE_IMPROVED")
        return 0

    print("[EVIDENCE] OZON_C37_PERSISTENT_PROFILE_NO_IMPROVEMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
