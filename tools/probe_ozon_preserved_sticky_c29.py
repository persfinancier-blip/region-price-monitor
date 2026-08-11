from __future__ import annotations

import argparse
import json
import platform
import re
import sys
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
from mobile_proxy import _decode_json, _parse_combined_proxy
from transport import ProxyContext

DEFAULT_SKU = "3129447770"
HOME_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
NEUTRAL_URL = "https://api.i.pn/json/"
LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
SESSION_RE = re.compile(r"-hold-session-session-([A-Za-z0-9]+)$", re.IGNORECASE)
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
            print(f"[INFO] Using cached sticky proxy: {LOCAL_PROXY_FILE}")
            return value
    raise ValueError(f"cached proxy not found: {LOCAL_PROXY_FILE}")


def _proxy_server(context: ProxyContext) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def _context_from_exact_bound_proxy(raw_proxy: str) -> tuple[ProxyContext, str]:
    proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
    match = SESSION_RE.search(proxy_user)
    if not match:
        raise ValueError("proxy username must already contain hold-session-session-<id>; C29 never rotates")
    session_id = match.group(1)
    context = ProxyContext.from_city(
        {
            "city": "ozon-c29-preserved-sticky",
            "proxy": proxy_server,
            "proxy_user": proxy_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )
    return context, session_id


def _neutral_ip_via_context(context: ProxyContext) -> str | None:
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
        return {ok: true, status: response.status, url: response.url, text};
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


def main() -> int:
    parser = argparse.ArgumentParser(description="C29: preserve exact operator-provided sticky proxy session; never rotate")
    parser.add_argument("--proxy")
    parser.add_argument("--sku", default=DEFAULT_SKU)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon preserved sticky C29 ===")
    print("EXACT cached hold-session-session-id. NO rotation. Same egress must survive into Camoufox.\n")

    try:
        raw_proxy = _load_proxy(args.proxy)
        context, session_id = _context_from_exact_bound_proxy(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] C29_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    print("[1/4] Proving exact cached sticky session without rotating ...")
    selected_ip = _neutral_ip_via_context(context)
    print(f"      preserved_session={session_id}")
    print(f"      selected_ip={selected_ip}")
    if not selected_ip:
        print("[EVIDENCE] OZON_C29_STICKY_IP_UNPROVEN")
        return 8

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

    print("[2/4] Starting Camoufox on this SAME preserved sticky ...")
    try:
        with Camoufox(**kwargs) as browser:
            page = browser.new_page()
            browser_ip = _browser_ip(page)
            print(f"      browser_ip={browser_ip}")
            if browser_ip != selected_ip:
                print("[EVIDENCE] OZON_C29_BROWSER_STICKY_IP_MISMATCH")
                return 8

            print("[3/4] Bootstrapping Ozon without replacing the sticky session ...")
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
            ua = page.evaluate("() => navigator.userAgent") or ""
            print(f"      cookies(all)={len(cookies)} unique_names={len(names)}")
            print(f"      cookie_names={','.join(names)}")
            print(f"      ui_challenge={ui_challenge}")
            print(f"      user_agent={ua[:100]}")

            print("[4/4] Fetching price through THIS SAME browser context ...")
            attempts: list[dict[str, Any]] = []
            for short, endpoint in ENDPOINTS:
                raw = _browser_fetch(page, endpoint, str(args.sku))
                if not raw.get("ok"):
                    err = str(raw.get("error") or "browser_fetch_failed")
                    attempts.append({"endpoint": short, "error": err})
                    print(f"      [{short}/browser-native] network={err}")
                    continue
                status = int(raw.get("status") or 0)
                text = str(raw.get("text") or "")
                payload = _decode_payload(text)
                if payload is not None and ozon._is_challenge(payload):
                    attempts.append({"endpoint": short, "status": status, "result": "challenge"})
                    print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> challenge")
                    continue
                parsed = ozon._parse_entrypoint_price(payload, str(args.sku)) if isinstance(payload, dict) else {"ok": False, "error": "not_json"}
                if parsed.get("ok"):
                    print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> PRICE")
                    print("\n" + "=" * 62)
                    print(f"PRICE: {parsed['price']:.0f} RUB")
                    if parsed.get("price_card"):
                        print(f"CARD:  {parsed['price_card']:.0f} RUB")
                    if parsed.get("price_original"):
                        print(f"ORIG:  {parsed['price_original']:.0f} RUB")
                    print(f"sticky_session: {session_id}")
                    print(f"sticky_ip: {selected_ip}")
                    print(f"cookies_in_browser_context: {len(cookies)}")
                    print(f"ui_challenge_seen: {ui_challenge}")
                    print("[EVIDENCE] OZON_PRESERVED_STICKY_PRICE_PROVEN")
                    print("=" * 62)
                    return 0
                err = parsed.get("error") or "parse_error"
                attempts.append({"endpoint": short, "status": status, "result": err})
                print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> {err}")

            print(f"      attempts={attempts}")
            print("[EVIDENCE] OZON_PRESERVED_STICKY_NO_PRICE")
            return 8
    except Exception as exc:
        print(f"[ERROR] C29_BROWSER_FAILED: {type(exc).__name__}: {context.redact(str(exc))}")
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
