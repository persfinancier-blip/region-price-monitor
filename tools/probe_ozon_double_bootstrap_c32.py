from __future__ import annotations

import argparse
import json
import platform
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

import ozon
from curl_transport import request_via_proxy as curl_request_via_proxy
from mobile_proxy import _decode_json, _parse_combined_proxy, rotate_session
from transport import ProxyContext

DEFAULT_SKU = "3129447770"
HOME_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
NEUTRAL_URL = "https://api.i.pn/json/"
LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
READY_COOKIE = "__Secure-ext_xcid"
ENDPOINTS = (
    ("entrypoint", "/api/entrypoint-api.bx/page/json/v2"),
    ("composer", "/api/composer-api.bx/page/json/v2"),
)
UI_CHALLENGE_MARKERS = (
    "captcha", "antibot", "доступ ограничен", "проверка безопасности", "challenge",
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


def _proxy_server(context: ProxyContext) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def _fresh_context(proxy_server: str, proxy_user: str, proxy_password: str) -> tuple[ProxyContext, str]:
    bound_user, session_id = rotate_session(proxy_user)
    context = ProxyContext.from_city(
        {
            "city": "ozon-c32-double-bootstrap",
            "proxy": proxy_server,
            "proxy_user": bound_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )
    return context, session_id


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


def _decode_payload(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads((text or "").lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _browser_fetch(page, endpoint: str, sku: str) -> dict[str, Any]:
    script = r"""
    async ({endpoint, sku}) => {
      const url = endpoint + "?url=" + encodeURIComponent("/product/" + sku + "/");
      try {
        const response = await fetch(url, {
          method: "GET",
          credentials: "include",
          redirect: "follow",
          referrer: "https://www.ozon.ru/product/" + sku + "/",
          referrerPolicy: "strict-origin-when-cross-origin",
          headers: {
            "Accept": "application/json",
            "x-o3-app-name": "dweb_client"
          }
        });
        const text = await response.text();
        return {ok: true, status: response.status, text};
      } catch (error) {
        return {ok: false, error: String(error && error.message ? error.message : error)};
      }
    }
    """
    return page.evaluate(script, {"endpoint": endpoint, "sku": str(sku)})


def _probe_api(page, sku: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for short, endpoint in ENDPOINTS:
        raw = _browser_fetch(page, endpoint, sku)
        if not raw.get("ok"):
            attempts.append({"endpoint": short, "error": str(raw.get("error") or "browser_fetch_failed")})
            continue
        status = int(raw.get("status") or 0)
        text = str(raw.get("text") or "")
        payload = _decode_payload(text)
        if payload is not None and ozon._is_challenge(payload):
            attempts.append({"endpoint": short, "status": status, "result": "challenge"})
            continue
        parsed = ozon._parse_entrypoint_price(payload, sku) if isinstance(payload, dict) else {"ok": False, "error": "not_json"}
        if parsed.get("ok"):
            return {
                "status": "price",
                "endpoint": short,
                "http_status": status,
                "price": parsed.get("price"),
                "price_card": parsed.get("price_card"),
                "price_original": parsed.get("price_original"),
                "attempts": attempts,
            }
        attempts.append({"endpoint": short, "status": status, "result": parsed.get("error") or "parse_error"})
    return {"status": "no_price", "attempts": attempts}


def _one_browser_run(Camoufox, context: ProxyContext, *, visible: bool, sku: str, run_no: int) -> dict[str, Any]:
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
        api_request_seen = False
        second_home = False
        first_error: str | None = None
        try:
            with page.expect_request("**/api/*-api.bx/page/json/v2**", timeout=30000):
                page.goto(HOME_URL, timeout=60000)
            api_request_seen = True
        except Exception as exc:
            first_error = type(exc).__name__
            second_home = True
            page.goto(HOME_URL, timeout=60000)
            page.wait_for_timeout(5000)
        page.wait_for_timeout(2500)

        cookies = list(page.context.cookies())
        names = sorted({str(c.get("name") or "") for c in cookies if c.get("name")})
        try:
            body = (page.text_content("body") or "")[:12000].lower()
        except Exception:
            body = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        ui_challenge = any(marker in body or marker in title for marker in UI_CHALLENGE_MARKERS)
        ua = page.evaluate("() => navigator.userAgent") or ""
        api = _probe_api(page, sku)

        mode = "visible" if visible else "headless"
        print(
            f"      run={run_no} mode={mode} api_request_seen={api_request_seen} second_home={second_home} "
            f"first_error={first_error or '-'} cookies={len(cookies)} unique={len(names)} "
            f"ext_xcid={READY_COOKIE in names} ui_challenge={ui_challenge} api={api.get('status')}"
        )
        print(f"      run={run_no} cookie_names={','.join(names)}")
        print(f"      run={run_no} user_agent={ua[:100]}")
        if api.get("status") == "price":
            print(f"      run={run_no} PRICE={float(api['price']):.0f} RUB endpoint={api.get('endpoint')}")

        return {
            "run": run_no,
            "mode": mode,
            "api_request_seen": api_request_seen,
            "second_home": second_home,
            "first_error": first_error,
            "cookie_count": len(cookies),
            "cookie_names": names,
            "ext_xcid": READY_COOKIE in names,
            "ui_challenge": ui_challenge,
            "user_agent": ua,
            "api": api,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="C32: reproduce the observed headless-fail -> visible-success pattern on one sticky session")
    parser.add_argument("--proxy")
    parser.add_argument("--sku", default=DEFAULT_SKU)
    args = parser.parse_args()

    print("=== Ozon double bootstrap C32 ===")
    print("ONE fresh sticky session. Run #1 HEADLESS, then Run #2 VISIBLE on the exact same sticky/IP.")
    print("No CAPTCHA interaction/submission. Cached proxy is used automatically.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
        context, session_id = _fresh_context(proxy_server, proxy_user, proxy_password)
    except Exception as exc:
        print(f"[ERROR] C32_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    selected_ip = _neutral_ip(context)
    print(f"[1/3] sticky_session={session_id} selected_ip={selected_ip or 'UNPROVEN'}")
    if not selected_ip:
        print("[EVIDENCE] OZON_C32_STICKY_IP_UNPROVEN")
        return 8

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        from camoufox import Camoufox

    try:
        print("[2/3] Run #1 HEADLESS on the sticky ...")
        first = _one_browser_run(Camoufox, context, visible=False, sku=str(args.sku), run_no=1)
        time.sleep(2)
        same_ip = _neutral_ip(context)
        print(f"      after_run1_ip={same_ip}")
        if same_ip != selected_ip:
            print("[EVIDENCE] OZON_C32_STICKY_CHANGED_AFTER_RUN1")
            return 8

        print("[3/3] Run #2 VISIBLE on the SAME sticky ...")
        second = _one_browser_run(Camoufox, context, visible=True, sku=str(args.sku), run_no=2)
        final_ip = _neutral_ip(context)
        print(f"      final_ip={final_ip}")
        if final_ip != selected_ip:
            print("[EVIDENCE] OZON_C32_STICKY_CHANGED_AFTER_RUN2")
            return 8

        print("\n=== C32 SUMMARY ===")
        for item in (first, second):
            api = item.get("api") or {}
            print(
                f"run={item['run']} mode={item['mode']} cookies={item['cookie_count']} "
                f"ext_xcid={item['ext_xcid']} ui_challenge={item['ui_challenge']} api={api.get('status')}"
            )

        if second.get("api", {}).get("status") == "price":
            print("[EVIDENCE] OZON_C32_SECOND_LAUNCH_PRICE_PROVEN")
            return 0
        if second.get("cookie_count", 0) > first.get("cookie_count", 0) or second.get("ext_xcid"):
            print("[EVIDENCE] OZON_C32_SECOND_LAUNCH_SESSION_IMPROVED")
            return 8
        print("[EVIDENCE] OZON_C32_SECOND_LAUNCH_NO_IMPROVEMENT")
        return 8
    except Exception as exc:
        print(f"[ERROR] C32_BROWSER_FAILED: {type(exc).__name__}: {context.redact(str(exc))}")
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
