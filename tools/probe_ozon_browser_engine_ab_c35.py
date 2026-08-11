from __future__ import annotations

import argparse
import json
import platform
import sys
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
OZON_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
NEUTRAL_URL = "https://api.i.pn/json/"
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
            "city": "ozon-c35-browser-engine-ab",
            "proxy": proxy_server,
            "proxy_user": bound_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )
    return context, session_id


def _proxy_server(context: ProxyContext) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def _neutral_ip(context: ProxyContext) -> str | None:
    outcome = curl_request_via_proxy(
        context,
        "GET",
        NEUTRAL_URL,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True,
    )
    payload = _decode_json(outcome.body) if outcome.ok else None
    return str((payload or {}).get("query") or "").strip() or None


def _security_details(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    getter = getattr(response, "security_details", None)
    if not callable(getter):
        return None
    try:
        details = getter()
    except Exception:
        return None
    return details if isinstance(details, dict) else None


def _page_observation(page: Any, response: Any, label: str) -> dict[str, Any]:
    page.wait_for_timeout(4500)
    try:
        body = (page.text_content("body") or "")[:12000].lower()
    except Exception:
        body = ""
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    ui_challenge = any(marker in body or marker in title for marker in UI_CHALLENGE_MARKERS)

    cookies = list(page.context.cookies())
    names = sorted({str(c.get("name") or "") for c in cookies if c.get("name")})
    state = page.evaluate(
        """() => ({
            href: location.href,
            protocol: location.protocol,
            secureContext: window.isSecureContext,
            ua: navigator.userAgent
        })"""
    )
    details = _security_details(response) or {}
    status = int(response.status) if response is not None else None

    result = {
        "label": label,
        "status": status,
        "final_url": str((state or {}).get("href") or page.url or ""),
        "protocol": str((state or {}).get("protocol") or ""),
        "secure_context": bool((state or {}).get("secureContext")),
        "user_agent": str((state or {}).get("ua") or ""),
        "cookie_count": len(cookies),
        "cookie_names": names,
        "ext_xcid": READY_COOKIE in names,
        "ui_challenge": ui_challenge,
        "tls_protocol": details.get("protocol"),
        "cert_subject": details.get("subjectName"),
        "cert_issuer": details.get("issuer"),
    }

    print(
        f"      {label}: status={status} cookies={len(cookies)} unique={len(names)} "
        f"ext_xcid={result['ext_xcid']} challenge={ui_challenge} secure={result['secure_context']}"
    )
    print(f"      {label}: cookie_names={','.join(names)}")
    print(f"      {label}: user_agent={result['user_agent'][:120]}")
    if result["tls_protocol"]:
        print(
            f"      {label}: tls={result['tls_protocol']} "
            f"subject={result['cert_subject']} issuer={result['cert_issuer']}"
        )
    return result


def _run_stock_firefox(context: ProxyContext, *, visible: bool) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    proxy = {
        "server": _proxy_server(context),
        "username": context.proxy_user,
        "password": context.proxy_password,
    }
    with sync_playwright() as pw:
        try:
            browser = pw.firefox.launch(headless=not visible, proxy=proxy)
        except Exception as exc:
            message = str(exc).lower()
            if "executable doesn't exist" in message or "executable does not exist" in message:
                raise RuntimeError("PLAYWRIGHT_FIREFOX_NOT_INSTALLED") from exc
            raise
        try:
            page = browser.new_page(locale="ru-RU")
            response = page.goto(OZON_URL, wait_until="domcontentloaded", timeout=60000)
            return _page_observation(page, response, "stock_firefox")
        finally:
            browser.close()


def _run_camoufox(context: ProxyContext, *, visible: bool) -> dict[str, Any]:
    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        from camoufox import Camoufox

    if visible:
        headless_mode: bool | str = False
    elif platform.system().lower() == "linux":
        headless_mode = "virtual"
    else:
        headless_mode = True

    kwargs: dict[str, Any] = {
        "os": "windows",
        "headless": headless_mode,
        "geoip": True,
        "humanize": 2.0,
        "locale": "ru-RU",
        "proxy": {
            "server": _proxy_server(context),
            "username": context.proxy_user,
            "password": context.proxy_password,
        },
    }
    with Camoufox(**kwargs) as browser:
        page = browser.new_page()
        response = page.goto(OZON_URL, wait_until="domcontentloaded", timeout=60000)
        return _page_observation(page, response, "camoufox")


def _material_outcome(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("status"),
        bool(item.get("ui_challenge")),
        bool(item.get("ext_xcid")),
        bool(item.get("secure_context")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="C35: stock Playwright Firefox vs Camoufox on one sticky proxy")
    parser.add_argument("--proxy")
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon browser-engine A/B diagnostic C35 ===")
    print("ONE sticky/IP. Stock Playwright Firefox first, Camoufox second.")
    print("Observation only: no CAPTCHA interaction/submission and no stealth tuning.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        context, session_id = _fresh_context(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] C35_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    before_ip = _neutral_ip(context)
    print(f"[1/4] sticky_session={session_id} before_ip={before_ip or 'UNPROVEN'}")
    if not before_ip:
        print("[EVIDENCE] OZON_C35_STICKY_IP_UNPROVEN")
        return 8

    print("[2/4] Stock Playwright Firefox on the exact sticky ...")
    try:
        stock = _run_stock_firefox(context, visible=args.visible)
    except RuntimeError as exc:
        if str(exc) == "PLAYWRIGHT_FIREFOX_NOT_INSTALLED":
            print("[EVIDENCE] OZON_C35_STOCK_FIREFOX_UNAVAILABLE")
            print("[INFO] Playwright Firefox browser binary is not installed in this environment.")
            return 8
        raise
    except Exception as exc:
        print(f"      stock_firefox_error={type(exc).__name__}: {context.redact(str(exc))}")
        stock = {"label": "stock_firefox", "error": type(exc).__name__}

    middle_ip = _neutral_ip(context)
    print(f"[3/4] after_stock_ip={middle_ip}")
    if middle_ip != before_ip:
        print("[EVIDENCE] OZON_C35_STICKY_CHANGED_BETWEEN_ENGINES")
        return 8

    print("[4/4] Camoufox on the SAME sticky ...")
    try:
        camo = _run_camoufox(context, visible=args.visible)
    except Exception as exc:
        print(f"      camoufox_error={type(exc).__name__}: {context.redact(str(exc))}")
        camo = {"label": "camoufox", "error": type(exc).__name__}

    after_ip = _neutral_ip(context)
    print(f"      after_camoufox_ip={after_ip}")
    if after_ip != before_ip:
        print("[EVIDENCE] OZON_C35_STICKY_CHANGED_AFTER_CAMOUFOX")
        return 8

    print("\n=== C35 SUMMARY ===")
    for item in (stock, camo):
        if item.get("error"):
            print(f"browser={item['label']} error={item['error']}")
        else:
            print(
                f"browser={item['label']} status={item.get('status')} cookies={item.get('cookie_count')} "
                f"ext_xcid={item.get('ext_xcid')} challenge={item.get('ui_challenge')} "
                f"secure={item.get('secure_context')}"
            )

    if stock.get("error") or camo.get("error"):
        print("[EVIDENCE] OZON_C35_ENGINE_COMPARISON_INCOMPLETE")
        return 8

    if _material_outcome(stock) != _material_outcome(camo):
        print("[EVIDENCE] OZON_C35_STOCK_FIREFOX_DIFFERS_FROM_CAMOUFOX")
        return 0

    print("[EVIDENCE] OZON_C35_BROWSERS_MATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
