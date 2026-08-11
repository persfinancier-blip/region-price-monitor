from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for p in (CORE, TOOLS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mobile_proxy import _parse_combined_proxy, rotate_session
from transport import ProxyContext

LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
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


def _fresh_proxy_context(raw_proxy: str) -> tuple[ProxyContext, str]:
    proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
    bound_user, session_id = rotate_session(proxy_user)
    context = ProxyContext.from_city(
        {
            "city": "ozon-c36-direct-vs-proxy",
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


def _security_details(response: Any) -> dict[str, Any]:
    if response is None:
        return {}
    getter = getattr(response, "security_details", None)
    if not callable(getter):
        return {}
    try:
        details = getter()
    except Exception:
        return {}
    return details if isinstance(details, dict) else {}


def _browser_ip(browser: Any) -> str | None:
    page = browser.new_page(locale="ru-RU")
    try:
        page.goto(IP_URL, wait_until="domcontentloaded", timeout=60000)
        text = page.text_content("body") or ""
        try:
            payload = json.loads(text)
        except Exception:
            payload = {}
        return str(payload.get("query") or "").strip() or None
    finally:
        page.close()


def _observe_ozon(browser: Any, label: str) -> dict[str, Any]:
    page = browser.new_page(locale="ru-RU")
    try:
        response = page.goto(OZON_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4500)

        try:
            body = (page.text_content("body") or "")[:12000].lower()
        except Exception:
            body = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""

        challenge = any(marker in body or marker in title for marker in UI_CHALLENGE_MARKERS)
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
        details = _security_details(response)
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
            "challenge": challenge,
            "tls_protocol": details.get("protocol"),
            "cert_subject": details.get("subjectName"),
            "cert_issuer": details.get("issuer"),
        }
        result["egress_ip"] = _browser_ip(browser)
        return result
    finally:
        page.close()


def _print_result(item: dict[str, Any]) -> None:
    print(
        f"      {item['label']}: status={item.get('status')} cookies={item.get('cookie_count')} "
        f"unique={len(item.get('cookie_names') or [])} ext_xcid={item.get('ext_xcid')} "
        f"challenge={item.get('challenge')} secure={item.get('secure_context')} ip={item.get('egress_ip')}"
    )
    print(f"      {item['label']}: cookie_names={','.join(item.get('cookie_names') or [])}")
    print(f"      {item['label']}: user_agent={str(item.get('user_agent') or '')[:120]}")
    if item.get("tls_protocol"):
        print(
            f"      {item['label']}: tls={item.get('tls_protocol')} "
            f"subject={item.get('cert_subject')} issuer={item.get('cert_issuer')}"
        )


def _material(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("status"),
        bool(item.get("challenge")),
        bool(item.get("ext_xcid")),
        item.get("cookie_count"),
        bool(item.get("secure_context")),
    )


def _healthy(item: dict[str, Any]) -> bool:
    status = item.get("status")
    return bool(
        isinstance(status, int)
        and 200 <= status < 400
        and not item.get("challenge")
        and item.get("secure_context")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="C36: stock Playwright Firefox direct vs mobile proxy")
    parser.add_argument("--proxy")
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon stock Firefox direct-vs-proxy diagnostic C36 ===")
    print("Same stock Playwright Firefox code. Arm A direct, Arm B mobile proxy.")
    print("Observation only: no CAPTCHA interaction/submission and no browser fingerprint tuning.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        proxy_context, session_id = _fresh_proxy_context(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] C36_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[ERROR] PLAYWRIGHT_IMPORT_FAILED: {type(exc).__name__}: {exc}")
        return 8

    with sync_playwright() as pw:
        print("[1/2] Stock Firefox DIRECT ...")
        direct_browser = pw.firefox.launch(headless=not args.visible)
        try:
            direct = _observe_ozon(direct_browser, "direct")
            _print_result(direct)
        finally:
            direct_browser.close()

        print(f"[2/2] Stock Firefox through mobile proxy sticky_session={session_id} ...")
        proxied_browser = pw.firefox.launch(headless=not args.visible, proxy=_proxy_dict(proxy_context))
        try:
            proxied = _observe_ozon(proxied_browser, "mobile_proxy")
            _print_result(proxied)
        finally:
            proxied_browser.close()

    print("\n=== C36 SUMMARY ===")
    for item in (direct, proxied):
        print(
            f"path={item['label']} status={item.get('status')} cookies={item.get('cookie_count')} "
            f"ext_xcid={item.get('ext_xcid')} challenge={item.get('challenge')} "
            f"secure={item.get('secure_context')} ip={item.get('egress_ip')}"
        )

    if _healthy(direct) and not _healthy(proxied):
        print("[EVIDENCE] OZON_C36_DIRECT_OK_PROXY_CHALLENGED")
        return 0
    if _material(direct) == _material(proxied):
        print("[EVIDENCE] OZON_C36_DIRECT_AND_PROXY_MATCH")
        return 0

    print("[EVIDENCE] OZON_C36_DIRECT_DIFFERS_FROM_PROXY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
