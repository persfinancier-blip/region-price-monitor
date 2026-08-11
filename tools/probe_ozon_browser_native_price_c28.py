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
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import ozon
from mobile_proxy import _parse_combined_proxy, find_mobile_proxy
from probe_ozon_single_run_c23 import _selected_context

DEFAULT_SKU = "3129447770"
HOME_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
NEUTRAL_URL = "https://api.i.pn/json/"
LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
ENDPOINTS = (
    ("entrypoint", "/api/entrypoint-api.bx/page/json/v2"),
    ("composer", "/api/composer-api.bx/page/json/v2"),
)
UI_CHALLENGE_MARKERS = (
    "captcha",
    "antibot",
    "доступ ограничен",
    "проверка безопасности",
    "challenge",
)


def _proxy_server(context) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def _cache_proxy(value: str) -> None:
    value = (value or "").strip()
    if not value:
        return
    LOCAL_PROXY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PROXY_FILE.write_text(value + "\n", encoding="utf-8")


def _load_proxy(cli_proxy: str | None) -> str:
    if cli_proxy and cli_proxy.strip():
        value = cli_proxy.strip()
        _cache_proxy(value)
        print(f"[INFO] Cached test proxy locally: {LOCAL_PROXY_FILE}")
        return value
    if LOCAL_PROXY_FILE.exists():
        value = LOCAL_PROXY_FILE.read_text(encoding="utf-8").strip()
        if value:
            print(f"[INFO] Using local cached proxy: {LOCAL_PROXY_FILE}")
            return value
    value = input("Proxy (VISIBLE host:port:user:pass, saved locally once): ").strip()
    _cache_proxy(value)
    if value:
        print(f"[INFO] Saved test proxy locally: {LOCAL_PROXY_FILE}")
    return value


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
        return {
          ok: true,
          status: response.status,
          url: response.url,
          text
        };
      } catch (error) {
        return {
          ok: false,
          error: String(error && error.message ? error.message : error)
        };
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
    parser = argparse.ArgumentParser(
        description="C28: one Camoufox browser + one sticky mobile proxy + browser-native Ozon API fetch"
    )
    parser.add_argument("--proxy", help="host:port:user:pass or scheme://host:port:user:pass")
    parser.add_argument("--sku", default=DEFAULT_SKU)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon browser-native price C28 ===")
    print("ONE browser. ONE sticky proxy/IP. Browser keeps its own full cookie jar and TLS/HTTP2 stack.")
    print("Browser-native API fetch. No CAPTCHA interaction/submission.\n")

    raw_proxy = _load_proxy(args.proxy)
    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(raw_proxy)
    except Exception as exc:
        print(f"[ERROR] PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    print("[1/4] Selecting fresh mobile sticky session ...")
    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-c28",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        print(f"[EVIDENCE] OZON_C28_MOBILE_PROXY_BLOCKED gate={selector.get('gate')}")
        return 8

    context, session_id, selected_ip = _selected_context(proxy_server, proxy_user, proxy_password, selected)
    print(f"      sticky_session={session_id} selected_ip={selected_ip}")

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

    print("[2/4] Starting Camoufox on THIS exact sticky session ...")
    try:
        with Camoufox(**kwargs) as browser:
            page = browser.new_page()
            browser_ip = _browser_ip(page)
            print(f"      browser_ip={browser_ip}")
            if browser_ip != selected_ip:
                print("[EVIDENCE] OZON_C28_BROWSER_STICKY_IP_MISMATCH")
                return 8

            print("[3/4] Bootstrapping Ozon in the same browser context ...")
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
            ui_challenge = any(m in body or m in title for m in UI_CHALLENGE_MARKERS)
            cookies = list(page.context.cookies())
            names = sorted({str(c.get("name") or "") for c in cookies if c.get("name")})
            ua = page.evaluate("() => navigator.userAgent") or ""
            print(f"      cookies(all)={len(cookies)} unique_names={len(names)}")
            print(f"      ui_challenge={ui_challenge}")
            print(f"      user_agent={ua[:100]}")

            print("[4/4] Fetching Ozon price THROUGH THIS SAME BROWSER NETWORK STACK ...")
            attempts: list[dict[str, Any]] = []
            for short, endpoint in ENDPOINTS:
                raw = _browser_fetch(page, endpoint, str(args.sku))
                if not raw.get("ok"):
                    error = str(raw.get("error") or "browser_fetch_failed")
                    attempts.append({"endpoint": short, "error": error})
                    print(f"      [{short}/browser-native] network={error}")
                    continue

                status = int(raw.get("status") or 0)
                text = str(raw.get("text") or "")
                payload = _decode_payload(text)
                if payload is not None and ozon._is_challenge(payload):
                    attempts.append({"endpoint": short, "status": status, "result": "challenge"})
                    print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> challenge")
                    continue

                parsed = (
                    ozon._parse_entrypoint_price(payload, str(args.sku))
                    if isinstance(payload, dict)
                    else {"ok": False, "error": "not_json"}
                )
                if parsed.get("ok"):
                    print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> PRICE")
                    print("\n" + "=" * 62)
                    print(f"PRICE: {parsed['price']:.0f} RUB")
                    if parsed.get("price_card"):
                        print(f"CARD:  {parsed['price_card']:.0f} RUB")
                    if parsed.get("price_original"):
                        print(f"ORIG:  {parsed['price_original']:.0f} RUB")
                    print(f"path: Camoufox/browser-native -> {short}")
                    print(f"sticky_ip: {selected_ip}")
                    print(f"cookies_in_browser_context: {len(cookies)}")
                    print(f"ui_challenge_seen: {ui_challenge}")
                    print("[EVIDENCE] OZON_BROWSER_NATIVE_PRICE_PROVEN")
                    print("=" * 62)
                    return 0

                error = parsed.get("error") or "parse_error"
                attempts.append({"endpoint": short, "status": status, "result": error})
                print(f"      [{short}/browser-native] HTTP {status}, {len(text)} b -> {error}")

            print(f"      attempts={attempts}")
            print("[EVIDENCE] OZON_BROWSER_NATIVE_NO_PRICE")
            return 8
    except Exception as exc:
        print(f"[ERROR] C28_BROWSER_FAILED: {type(exc).__name__}: {context.redact(str(exc))}")
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
