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
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import ozon
from curl_cffi import requests as creq
from mobile_proxy import _decode_json, _parse_combined_proxy, find_mobile_proxy
from probe_ozon_single_run_c23 import _selected_context

DEFAULT_SKU = "3129447770"
HOME_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"
NEUTRAL_URL = "https://api.i.pn/json/"
ENDPOINTS = (
    ("entrypoint", "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"),
    ("composer", "https://www.ozon.ru/api/composer-api.bx/page/json/v2"),
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


def _browser_family(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "firefox/" in ua:
        return "firefox"
    if "edg/" in ua or "edge/" in ua:
        return "edge"
    if "chrome/" in ua or "chromium/" in ua:
        return "chrome"
    if "safari/" in ua and "chrome/" not in ua and "chromium/" not in ua:
        return "safari"
    return "unknown"


def _browser_version(user_agent: str, family: str) -> str | None:
    patterns = {
        "firefox": r"Firefox/([0-9.]+)",
        "edge": r"(?:Edg|Edge)/([0-9.]+)",
        "chrome": r"(?:Chrome|Chromium)/([0-9.]+)",
        "safari": r"Version/([0-9.]+)",
    }
    pattern = patterns.get(family)
    if not pattern:
        return None
    match = re.search(pattern, user_agent or "", re.IGNORECASE)
    return match.group(1) if match else None


def _curl_target_for_family(family: str) -> str | None:
    # Fail-closed: never mix a Firefox browser session with a Chrome TLS target.
    return {
        "firefox": "firefox",
        "chrome": "chrome",
        "safari": "safari",
    }.get(family)


def _copy_all_cookies(session: Any, cookies: list[dict[str, Any]]) -> int:
    """Copy every browser cookie without flattening duplicate cookie names.

    Domain/path are preserved. Cookie values remain memory-only.
    """
    copied = 0
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        if not name:
            continue
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "") or None
        path = str(cookie.get("path") or "/") or "/"
        kwargs: dict[str, Any] = {"path": path}
        if domain:
            kwargs["domain"] = domain
        session.cookies.set(name, value, **kwargs)
        copied += 1
    return copied


def _browser_bootstrap(context, *, visible: bool) -> dict[str, Any]:
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

        # Browser must use the exact same bound mobile sticky session.
        page.goto(NEUTRAL_URL, timeout=60000)
        neutral_text = page.text_content("body") or ""
        try:
            neutral = json.loads(neutral_text)
        except Exception:
            neutral = {}
        browser_ip = str(neutral.get("query") or "").strip() or None

        # Bootstrap Ozon. UI challenge is only recorded; it is not interacted with.
        page.goto(HOME_URL, timeout=60000)
        page.wait_for_timeout(4500)
        try:
            body = (page.text_content("body") or "")[:12000].lower()
        except Exception:
            body = ""
        ui_challenge = any(marker in body for marker in UI_CHALLENGE_MARKERS)
        try:
            title = page.title() or ""
        except Exception:
            title = ""
        if any(marker in title.lower() for marker in UI_CHALLENGE_MARKERS):
            ui_challenge = True

        # Keep the full browser cookie jar, including domain/path scoped duplicates.
        cookies = list(page.context.cookies())
        user_agent = page.evaluate("() => navigator.userAgent") or ""
        family = _browser_family(user_agent)
        version = _browser_version(user_agent, family)

    return {
        "browser_ip": browser_ip,
        "cookies": cookies,
        "cookie_count": len(cookies),
        "user_agent": user_agent,
        "browser_family": family,
        "browser_version": version,
        "ui_challenge": ui_challenge,
    }


def _curl_session(*, user_agent: str, family: str, cookies: list[dict[str, Any]]) -> tuple[Any, str]:
    target = _curl_target_for_family(family)
    if target is None:
        raise ValueError(f"unsupported browser family for coherent curl handoff: {family}")

    session = creq.Session(impersonate=target)
    copied = _copy_all_cookies(session, cookies)
    expected = len([cookie for cookie in cookies if cookie.get("name")])
    if copied != expected:
        raise ValueError(f"cookie transfer incomplete: copied={copied} expected={expected}")
    session.headers.update({
        "User-Agent": user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    return session, target


def _session_get(session: Any, context, url: str, **kwargs: Any):
    return session.get(
        url,
        proxy=_proxy_server(context),
        proxy_auth=(context.proxy_user, context.proxy_password),
        timeout=45,
        allow_redirects=True,
        **kwargs,
    )


def _curl_ip(session: Any, context) -> str | None:
    response = _session_get(session, context, NEUTRAL_URL)
    try:
        payload = response.json()
    except Exception:
        payload = _decode_json(response.content)
    return str((payload or {}).get("query") or "").strip() or None


def _fetch_price(session: Any, context, *, sku: str, target: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Referer": f"https://www.ozon.ru/product/{sku}/",
        "x-o3-app-name": "dweb_client",
    }
    attempts: list[dict[str, Any]] = []

    for short, endpoint in ENDPOINTS:
        try:
            response = _session_get(
                session,
                context,
                endpoint,
                params={"url": f"/product/{sku}/"},
                headers=headers,
            )
        except Exception as exc:
            attempts.append({"endpoint": short, "error": type(exc).__name__})
            print(f"      [{short}/{target}] network={type(exc).__name__}")
            continue

        body = response.text or ""
        try:
            decoded = json.loads(body.lstrip("\ufeff \t\r\n"))
            payload = decoded if isinstance(decoded, dict) else None
        except Exception:
            payload = None

        if payload is not None and ozon._is_challenge(payload):
            attempts.append({"endpoint": short, "status": int(response.status_code), "result": "challenge"})
            print(f"      [{short}/{target}] HTTP {response.status_code}, {len(body)} b -> challenge")
            continue

        parsed = (
            ozon._parse_entrypoint_price(payload, str(sku))
            if isinstance(payload, dict)
            else {"ok": False, "error": "not_json"}
        )
        if parsed.get("ok"):
            result = dict(parsed)
            result.pop("ok", None)
            result.update({
                "status": "price",
                "endpoint": short,
                "target": target,
                "http_status": int(response.status_code),
                "attempts": attempts,
            })
            print(f"      [{short}/{target}] HTTP {response.status_code}, {len(body)} b -> PRICE")
            return result

        error = parsed.get("error") or "parse_error"
        attempts.append({"endpoint": short, "status": int(response.status_code), "result": error})
        print(f"      [{short}/{target}] HTTP {response.status_code}, {len(body)} b -> {error}")

    return {"status": "no_price", "attempts": attempts, "target": target}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="C27: one sticky proxy + full browser cookie jar + same browser-family curl handoff"
    )
    parser.add_argument("--proxy", help="host:port:user:pass or scheme://host:port:user:pass")
    parser.add_argument("--sku", default=DEFAULT_SKU)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon session coherence C27 ===")
    print("ONE sticky mobile session. ALL browser cookies. Same browser-family TLS target.")
    print("No CAPTCHA interaction/submission. Cookie values are memory-only.\n")

    raw_proxy = args.proxy or input("Proxy (VISIBLE host:port:user:pass): ").strip()
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
        city_label="ozon-c27",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        print(f"[EVIDENCE] OZON_C27_MOBILE_PROXY_BLOCKED gate={selector.get('gate')}")
        return 8

    context, session_id, selected_ip = _selected_context(
        proxy_server, proxy_user, proxy_password, selected
    )
    print(f"      sticky_session={session_id} selected_ip={selected_ip}")

    print("[2/4] Camoufox bootstrap on THIS exact sticky session ...")
    try:
        browser = _browser_bootstrap(context, visible=args.visible)
    except Exception as exc:
        print(f"[ERROR] BROWSER_BOOTSTRAP_FAILED: {type(exc).__name__}: {context.redact(str(exc))}")
        return 8

    print(f"      browser_ip={browser['browser_ip']}")
    print(f"      browser={browser['browser_family']} {browser['browser_version'] or '?'}")
    print(f"      cookies(all)={browser['cookie_count']}")
    print(f"      ui_challenge={browser['ui_challenge']}")
    if browser["browser_ip"] != selected_ip:
        print("[EVIDENCE] OZON_C27_BROWSER_STICKY_IP_MISMATCH")
        return 8

    target = _curl_target_for_family(browser["browser_family"])
    if not target:
        print(f"[EVIDENCE] OZON_C27_BROWSER_FAMILY_UNSUPPORTED family={browser['browser_family']}")
        return 8
    print(f"      handshake_family: browser={browser['browser_family']} curl={target} MATCH")

    print("[3/4] Creating curl_cffi session with ALL cookies + same sticky proxy ...")
    try:
        session, target = _curl_session(
            user_agent=browser["user_agent"],
            family=browser["browser_family"],
            cookies=browser["cookies"],
        )
        curl_ip = _curl_ip(session, context)
    except Exception as exc:
        print(f"[ERROR] CURL_SESSION_FAILED: {type(exc).__name__}: {context.redact(str(exc))}")
        return 8

    print(f"      curl_ip={curl_ip}")
    print("      user_agent_exact=true")
    print(f"      cookie_count_transferred={browser['cookie_count']}")
    if curl_ip != selected_ip or curl_ip != browser["browser_ip"]:
        print("[EVIDENCE] OZON_C27_CURL_STICKY_IP_MISMATCH")
        return 8

    print("[4/4] Ozon price request with coherent session ...")
    result = _fetch_price(session, context, sku=str(args.sku), target=target)
    if result.get("status") == "price":
        print("\n" + "=" * 62)
        print(f"PRICE: {result['price']:.0f} RUB")
        if result.get("price_card"):
            print(f"CARD:  {result['price_card']:.0f} RUB")
        if result.get("price_original"):
            print(f"ORIG:  {result['price_original']:.0f} RUB")
        print(
            f"path: Camoufox/{browser['browser_family']} -> "
            f"curl_cffi/{target} -> {result['endpoint']}"
        )
        print(f"sticky_ip: {selected_ip}")
        print(f"cookies_transferred: {browser['cookie_count']} (values not persisted)")
        print("[EVIDENCE] OZON_SESSION_COHERENCE_PRICE_PROVEN")
        print("=" * 62)
        return 0

    print("[EVIDENCE] OZON_SESSION_COHERENCE_NO_PRICE")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
