from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge
from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext, ProxyContextError, TransportOutcome

DEFAULT_OZON_SKU = "3129447770"
OZON_HOME = "https://www.ozon.ru/"
OZON_PRODUCT = "https://www.ozon.ru/product/{sku}/"
ENTRYPOINT_MARKER = "/api/entrypoint-api.bx/page/json/v2"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_zero_human_bootstrap_report.json"
STATE_FILE = LOCAL_PROBES / "ozon_zero_human_storage_state.json"
RAW_FILE = LOCAL_PROBES / "ozon_zero_human_entrypoint.json"
SCREENSHOT_FILE = LOCAL_PROBES / "ozon_zero_human_browser.png"

# Only replay bounded non-secret frontend headers observed from the live browser.
SAFE_REPLAY_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "referer",
    "user-agent",
    "x-o3-app-name",
    "x-o3-app-version",
    "x-o3-manifest-version",
    "x-o3-parent-requestid",
    "x-page-view-id",
}
SECRET_HEADER_NAMES = {"cookie", "authorization", "proxy-authorization"}
ANTIBOT_MARKERS = (
    "captcha",
    "капча",
    "antibot",
    "доступ ограничен",
    "checking your browser",
    "challenge-platform",
)


def _body_text(body: str | bytes | None) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _sha256(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else None


def _entrypoint_for_sku(url: str, sku: str) -> bool:
    parsed = urlsplit(url)
    if ENTRYPOINT_MARKER not in parsed.path:
        return False
    target = parse_qs(parsed.query).get("url", [""])[0]
    return target.rstrip("/") == f"/product/{sku}"


def _safe_replay_headers(headers: dict[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        low = key.lower()
        if low in SECRET_HEADER_NAMES:
            continue
        if low in SAFE_REPLAY_HEADERS:
            safe[low] = value
    return safe


def _antibot(title: str, body: str) -> bool:
    sample = f"{title}\n{body[:5000]}".lower()
    return any(marker in sample for marker in ANTIBOT_MARKERS)


def _json_shape(text: str) -> tuple[bool, list[str] | None, int | None]:
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return False, None, None
    if not isinstance(payload, dict):
        return True, None, None
    keys = sorted(str(key) for key in payload.keys())[:80]
    widget_states = payload.get("widgetStates")
    return True, keys, len(widget_states) if isinstance(widget_states, dict) else None


def _outcome_or_none(outcome: TransportOutcome | None) -> dict[str, Any] | None:
    return outcome.safe_dict() if outcome is not None else None


def main() -> int:
    print("=== Ozon zero-human bootstrap probe ===")
    print("Headless Playwright creates session state automatically, then closes.")
    print("curl_cffi replays the browser-observed current entrypoint request through the same ProxyContext.")
    print("No login, no manual captcha, no city/PVZ selection, no browser input in C08.")

    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_OZON_SKU}]: ").strip() or DEFAULT_OZON_SKU

    try:
        context = ProxyContext.from_city(
            {
                "city": city,
                "proxy": proxy,
                "proxy_user": proxy_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except ProxyContextError as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] PLAYWRIGHT_NOT_INSTALLED")
        print("Run tests\\SETUP_OZON_BOOTSTRAP.bat on Windows or tests/setup_ozon_bootstrap.sh on Linux.")
        return 10

    captured: dict[str, Any] | None = None
    browser_title = ""
    browser_body = ""
    browser_error: str | None = None
    cookies: list[dict[str, Any]] = []
    bridge_state: dict[str, Any] | None = None

    try:
        with LocalBrowserProxyBridge(context) as bridge:
            bridge_state = bridge.safe_state
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    proxy={"server": bridge.proxy_url},
                    args=["--disable-dev-shm-usage"],
                )
                browser_context = browser.new_context(locale="ru-RU")
                page = browser_context.new_page()

                def observe(request: Any) -> None:
                    nonlocal captured
                    if captured is not None:
                        return
                    if not _entrypoint_for_sku(request.url, sku):
                        return
                    headers = {str(k).lower(): str(v) for k, v in request.headers.items()}
                    captured = {
                        "url": request.url,
                        "headers": _safe_replay_headers(headers),
                    }

                page.on("request", observe)
                try:
                    page.goto(OZON_HOME, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    page.goto(OZON_PRODUCT.format(sku=sku), wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(7000)
                except Exception as exc:
                    browser_error = context.redact(f"{type(exc).__name__}: {exc}")

                try:
                    browser_title = (page.title() or "")[:200]
                except Exception:
                    browser_title = ""
                try:
                    browser_body = (page.locator("body").inner_text(timeout=5000) or "")[:12000]
                except Exception:
                    browser_body = ""
                try:
                    page.screenshot(path=str(SCREENSHOT_FILE), full_page=False)
                except Exception:
                    pass

                cookies = browser_context.cookies(["https://www.ozon.ru/"])
                browser_context.storage_state(path=str(STATE_FILE))
                browser_context.close()
                browser.close()
            bridge_state = bridge.safe_state
    except Exception as exc:
        browser_error = context.redact(f"{type(exc).__name__}: {exc}")

    # Playwright is now fully closed. Only curl_cffi is allowed below this point.
    cookie_dict = {
        str(cookie.get("name")): str(cookie.get("value"))
        for cookie in cookies
        if cookie.get("name") and cookie.get("value") is not None
    }

    replay: TransportOutcome | None = None
    replay_text = ""
    json_ok = False
    top_level_keys: list[str] | None = None
    widget_state_count: int | None = None

    if captured is not None:
        replay = curl_request_via_proxy(
            context,
            "GET",
            str(captured["url"]),
            headers=dict(captured["headers"]),
            cookies=cookie_dict,
            impersonate="chrome",
            timeout=45,
            allow_redirects=True,
        )
        replay_text = _body_text(replay.body)
        if replay_text:
            RAW_FILE.write_text(replay_text, encoding="utf-8", errors="replace")
        json_ok, top_level_keys, widget_state_count = _json_shape(replay_text)

    challenged = _antibot(browser_title, browser_body)
    if browser_error and not captured and not cookies:
        gate = "OZON_ZERO_HUMAN_BROWSER_FAILED"
    elif challenged and captured is None:
        gate = "OZON_ZERO_HUMAN_BROWSER_CHALLENGED"
    elif captured is None:
        gate = "OZON_ZERO_HUMAN_ENTRYPOINT_NOT_OBSERVED"
    elif replay is None or replay.status_code is None:
        gate = "OZON_ZERO_HUMAN_ENTRYPOINT_REPLAY_TRANSPORT_FAILED"
    elif replay.status_code != 200:
        gate = "OZON_ZERO_HUMAN_ENTRYPOINT_REPLAY_BLOCKED"
    elif not json_ok:
        gate = "OZON_ZERO_HUMAN_ENTRYPOINT_NON_JSON"
    else:
        gate = "OZON_ZERO_HUMAN_BOOTSTRAP_AND_ENTRYPOINT_PROVEN"

    report = {
        "goal": "ozon_zero_human_session_bootstrap_then_entrypoint_replay",
        "proxy_context": context.safe_identity,
        "browser": {
            "engine": "playwright_chromium",
            "headless": True,
            "user_interaction": False,
            "login_attempted": False,
            "manual_region_or_pvz": False,
            "bridge": bridge_state,
            "navigation_error": browser_error,
            "title": browser_title,
            "antibot_marker": challenged,
            "cookie_count": len(cookies),
            "storage_state_saved_local": STATE_FILE.exists(),
            "screenshot_saved_local": SCREENSHOT_FILE.exists(),
        },
        "entrypoint_capture": {
            "observed": captured is not None,
            "requested_sku": sku,
            "url": captured.get("url") if captured else None,
            "safe_header_names": sorted(captured.get("headers", {}).keys()) if captured else [],
            "secret_headers_persisted": False,
        },
        "steady_state_replay": {
            "browser_closed_before_replay": True,
            "transport": _outcome_or_none(replay),
            "body_chars": len(replay_text),
            "body_sha256": _sha256(replay_text),
            "json_decoded": json_ok,
            "top_level_keys": top_level_keys,
            "widget_state_count": widget_state_count,
            "price_parsed": False,
            "local_body_file": str(RAW_FILE) if replay_text else None,
        },
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Storage state, screenshot and raw response are local/Git-ignored and may contain session material.")
    if gate == "OZON_ZERO_HUMAN_BOOTSTRAP_AND_ENTRYPOINT_PROVEN":
        print("[PASS] OZON_ZERO_HUMAN_BOOTSTRAP_AND_ENTRYPOINT_PROVEN")
        return 0
    print(f"[EVIDENCE] {gate}")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
