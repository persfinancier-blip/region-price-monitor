from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge
from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext, ProxyContextError

NEUTRAL_URL = "https://api.i.pn/json/"
DEFAULT_OZON_SKU = "3129447770"
OZON_PRODUCT = "https://www.ozon.ru/product/{sku}/"
ENTRYPOINT_MARKER = "/api/entrypoint-api.bx/page/json/v2"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_access_discriminator_report.json"
HEADLESS_SCREENSHOT = LOCAL_PROBES / "ozon_access_headless.png"
HEADED_SCREENSHOT = LOCAL_PROBES / "ozon_access_headed.png"

DENIAL_MARKERS = (
    "похоже, нет соединения",
    "выключите vpn",
    "обратиться в поддержку",
)
ANTIBOT_MARKERS = (
    "captcha",
    "капча",
    "antibot",
    "доступ ограничен",
    "checking your browser",
    "challenge-platform",
)
_INCIDENT_RE = re.compile(r"(?:инцидент|incident)\s*:\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _safe_identity(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "query": payload.get("query"),
        "countryCode": payload.get("countryCode"),
        "regionName": payload.get("regionName"),
        "city": payload.get("city"),
        "mobile": payload.get("mobile"),
        "proxy": payload.get("proxy"),
        "hosting": payload.get("hosting"),
    }


def _same_identity(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    return all(left.get(key) == right.get(key) for key in ("query", "countryCode", "regionName", "city"))


def _classify_page(title: str, body: str) -> dict[str, Any]:
    sample = f"{title}\n{body[:12000]}".lower()
    denial = any(marker in sample for marker in DENIAL_MARKERS)
    antibot = any(marker in sample for marker in ANTIBOT_MARKERS)
    incident = _INCIDENT_RE.search(f"{title}\n{body[:12000]}")
    return {
        "network_denial_marker": denial,
        "antibot_marker": antibot,
        "incident_id_present": incident is not None,
    }


def _run_browser_mode(p: Any, context: ProxyContext, sku: str, *, headless: bool, screenshot: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "headless": headless,
        "neutral_identity": None,
        "neutral_error": None,
        "ozon_navigation_error": None,
        "document_status": None,
        "title": "",
        "entrypoint_observed": False,
        "network_denial_marker": False,
        "antibot_marker": False,
        "incident_id_present": False,
        "bridge": None,
        "screenshot_saved_local": False,
    }
    try:
        with LocalBrowserProxyBridge(context) as bridge:
            result["bridge"] = bridge.safe_state
            browser = p.chromium.launch(
                headless=headless,
                proxy={"server": bridge.proxy_url},
                args=["--disable-dev-shm-usage"],
            )
            browser_context = browser.new_context(locale="ru-RU")
            page = browser_context.new_page()
            entrypoint_observed = False

            def observe(request: Any) -> None:
                nonlocal entrypoint_observed
                if ENTRYPOINT_MARKER in request.url and f"/product/{sku}" in request.url:
                    entrypoint_observed = True

            page.on("request", observe)
            try:
                neutral_response = page.goto(NEUTRAL_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(800)
                neutral_text = page.locator("body").inner_text(timeout=5000) or ""
                result["neutral_identity"] = _safe_identity(neutral_text)
                if neutral_response is not None:
                    result["neutral_status"] = neutral_response.status
            except Exception as exc:
                result["neutral_error"] = context.redact(f"{type(exc).__name__}: {exc}")

            try:
                response = page.goto(OZON_PRODUCT.format(sku=sku), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(7000)
                if response is not None:
                    result["document_status"] = response.status
            except Exception as exc:
                result["ozon_navigation_error"] = context.redact(f"{type(exc).__name__}: {exc}")

            try:
                result["title"] = (page.title() or "")[:200]
            except Exception:
                pass
            try:
                body = (page.locator("body").inner_text(timeout=5000) or "")[:12000]
            except Exception:
                body = ""
            result.update(_classify_page(result["title"], body))
            result["entrypoint_observed"] = entrypoint_observed
            try:
                page.screenshot(path=str(screenshot), full_page=False)
                result["screenshot_saved_local"] = screenshot.exists()
            except Exception:
                pass
            browser_context.close()
            browser.close()
            result["bridge"] = bridge.safe_state
    except Exception as exc:
        result["browser_error"] = context.redact(f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    print("=== Ozon access discriminator C09 ===")
    print("Zero-user diagnostic: compare headless and headed Playwright through the same ProxyContext.")
    print("The headed window may appear briefly; do not click or type in it.")

    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_OZON_SKU}]: ").strip() or DEFAULT_OZON_SKU

    try:
        context = ProxyContext.from_city(
            {"city": city, "proxy": proxy, "proxy_user": proxy_user, "proxy_password": proxy_password},
            require_explicit_scheme=True,
        )
    except ProxyContextError as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {exc}")
        return 2

    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    neutral_identity = _safe_identity(_body_text(neutral.body)) if neutral.ok else None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] PLAYWRIGHT_NOT_INSTALLED")
        return 10

    with sync_playwright() as p:
        headless_result = _run_browser_mode(p, context, sku, headless=True, screenshot=HEADLESS_SCREENSHOT)
        headed_result = _run_browser_mode(p, context, sku, headless=False, screenshot=HEADED_SCREENSHOT)

    binding_ok = (
        neutral_identity is not None
        and _same_identity(neutral_identity, headless_result.get("neutral_identity"))
        and _same_identity(neutral_identity, headed_result.get("neutral_identity"))
    )
    headless_denied = bool(headless_result.get("network_denial_marker"))
    headed_denied = bool(headed_result.get("network_denial_marker"))
    headless_entrypoint = bool(headless_result.get("entrypoint_observed"))
    headed_entrypoint = bool(headed_result.get("entrypoint_observed"))

    if not binding_ok:
        gate = "OZON_BROWSER_PROXY_BINDING_UNPROVEN"
    elif headless_entrypoint:
        gate = "OZON_ENTRYPOINT_OBSERVED_HEADLESS"
    elif headless_denied and headed_entrypoint:
        gate = "OZON_HEADLESS_SPECIFIC_DENIAL_EVIDENCED"
    elif headless_denied and not headed_denied:
        gate = "OZON_HEADLESS_SPECIFIC_DENIAL_EVIDENCED"
    elif headless_denied and headed_denied:
        gate = "OZON_ROUTE_DENIED_BOTH_BROWSER_MODES"
    elif headed_entrypoint:
        gate = "OZON_ENTRYPOINT_OBSERVED_HEADED"
    else:
        gate = "OZON_ACCESS_DISCRIMINATOR_INCONCLUSIVE"

    report = {
        "goal": "ozon_access_failure_discriminator",
        "proxy_context": context.safe_identity,
        "curl_neutral": {"transport": neutral.safe_dict(), "identity": neutral_identity},
        "headless": headless_result,
        "headed": headed_result,
        "proxy_binding_same_identity_all_modes": binding_ok,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Screenshots are local/Git-ignored. No browser interaction is required or accepted.")
    print(f"[EVIDENCE] {gate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
