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
            "city": "ozon-c30-session-quality",
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


def _browser_ip(page) -> str | None:
    page.goto(NEUTRAL_URL, timeout=60000)
    text = page.text_content("body") or ""
    try:
        payload = json.loads(text)
    except Exception:
        payload = {}
    return str(payload.get("query") or "").strip() or None


def _browser_fetch(page, endpoint: str, sku: str) -> dict[str, Any]:
    script = r"""
    async ({endpoint, sku}) => {
      const url = endpoint + "?url=" + encodeURIComponent("/product/" + sku + "/");
      try {
        const response = await fetch(url, {
          method: "GET",
          credentials: "include",
          redirect: "follow",
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


def _decode_payload(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads((text or "").lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


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
        parsed = (
            ozon._parse_entrypoint_price(payload, sku)
            if isinstance(payload, dict)
            else {"ok": False, "error": "not_json"}
        )
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


def main() -> int:
    parser = argparse.ArgumentParser(description="C30: compare fresh sticky sessions by Ozon cookie/bootstrap quality")
    parser.add_argument("--proxy")
    parser.add_argument("--sku", default=DEFAULT_SKU)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    if args.attempts < 1 or args.attempts > 10:
        print("[ERROR] attempts must be 1..10")
        return 2

    print("=== Ozon fresh sticky session quality C30 ===")
    print("Fresh sticky per attempt; same sticky is preserved inside the attempt.")
    print("Observe cookie bootstrap + browser-native API. No CAPTCHA interaction/submission.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] C30_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        from camoufox import Camoufox

    if args.visible:
        headless_mode: bool | str = False
    elif platform.system().lower() == "linux":
        headless_mode = "virtual"
    else:
        headless_mode = True

    summary: list[dict[str, Any]] = []
    for index in range(1, args.attempts + 1):
        context, session_id = _fresh_context(proxy_server, proxy_user, proxy_password)
        selected_ip = _neutral_ip(context)
        print(f"[{index}/{args.attempts}] session={session_id} ip={selected_ip or 'UNPROVEN'}")
        if not selected_ip:
            summary.append({"attempt": index, "session_id": session_id, "result": "ip_unproven"})
            continue

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

        try:
            with Camoufox(**kwargs) as browser:
                page = browser.new_page()
                browser_ip = _browser_ip(page)
                if browser_ip != selected_ip:
                    print(f"      browser_ip={browser_ip} -> STICKY_MISMATCH")
                    summary.append({
                        "attempt": index,
                        "session_id": session_id,
                        "ip": selected_ip,
                        "browser_ip": browser_ip,
                        "result": "sticky_mismatch",
                    })
                    continue

                page.goto(HOME_URL, timeout=60000)
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
                ready_cookie = READY_COOKIE in names
                api = _probe_api(page, str(args.sku))

                print(
                    f"      browser_ip={browser_ip} cookies={len(cookies)} unique={len(names)} "
                    f"ext_xcid={ready_cookie} ui_challenge={ui_challenge} api={api.get('status')}"
                )
                if api.get("status") == "price":
                    print(f"      PRICE={float(api['price']):.0f} RUB endpoint={api.get('endpoint')}")

                item = {
                    "attempt": index,
                    "session_id": session_id,
                    "ip": selected_ip,
                    "cookie_count": len(cookies),
                    "cookie_names": names,
                    "ext_xcid": ready_cookie,
                    "ui_challenge": ui_challenge,
                    "api": api,
                }
                summary.append(item)

                if api.get("status") == "price":
                    print("[EVIDENCE] OZON_C30_FRESH_STICKY_PRICE_PROVEN")
                    return 0
        except Exception as exc:
            print(f"      browser_error={type(exc).__name__}: {context.redact(str(exc))}")
            summary.append({"attempt": index, "session_id": session_id, "ip": selected_ip, "result": "browser_error"})

        if index < args.attempts:
            time.sleep(3)

    print("\n=== C30 SUMMARY ===")
    for item in summary:
        if "cookie_count" in item:
            api = item.get("api") or {}
            print(
                f"attempt={item['attempt']} ip={item.get('ip')} cookies={item.get('cookie_count')} "
                f"ext_xcid={item.get('ext_xcid')} ui_challenge={item.get('ui_challenge')} api={api.get('status')}"
            )
        else:
            print(f"attempt={item.get('attempt')} ip={item.get('ip')} result={item.get('result')}")
    print("[EVIDENCE] OZON_C30_NO_READY_SESSION_FOUND")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
