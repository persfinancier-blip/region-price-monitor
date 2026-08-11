from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext, ProxyContextError
from probe_ozon_access_discriminator import (
    NEUTRAL_URL,
    DEFAULT_OZON_SKU,
    ENTRYPOINT_MARKER,
    OZON_PRODUCT,
    _body_text,
    _safe_identity,
    _same_identity,
    _classify_page,
    _browser_fetch_text,
)

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_native_headed_c14_report.json"
SCREENSHOT_FILE = LOCAL_PROBES / "ozon_native_headed_c14.png"
STORAGE_FILE = LOCAL_PROBES / "ozon_native_headed_c14_storage_state.json"


def _native_proxy(context: ProxyContext) -> dict[str, str]:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return {
        "server": f"{context.scheme}://{host}:{context.port}",
        "username": context.proxy_user,
        "password": context.proxy_password,
    }


def main() -> int:
    print("=== Ozon native headed Chromium access C14 ===")
    print("ONE ProxyContext. Normal Chromium uses Playwright native proxy settings; no custom bridge.")
    print("Do NOT click, type or solve captcha. The browser will close automatically.")

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
    curl_identity = _safe_identity(_body_text(neutral.body)) if neutral.ok else None

    result: dict[str, Any] = {
        "headless": False,
        "native_proxy": True,
        "neutral_identity": None,
        "neutral_error": None,
        "ozon_navigation_error": None,
        "document_status": None,
        "title": "",
        "entrypoint_observed": False,
        "network_denial_marker": False,
        "antibot_marker": False,
        "incident_id_present": False,
        "screenshot_saved_local": False,
        "storage_state_saved_local": False,
        "cookie_count": 0,
        "cookie_names": [],
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] PLAYWRIGHT_NOT_INSTALLED")
        return 10

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                proxy=_native_proxy(context),
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
                page.wait_for_timeout(500)
                fetched = _browser_fetch_text(page, NEUTRAL_URL)
                result["neutral_identity"] = _safe_identity(fetched.get("text") or "")
                result["neutral_fetch"] = {
                    "ok": fetched.get("ok"),
                    "status": fetched.get("status"),
                    "error": fetched.get("error"),
                }
                result["neutral_status"] = neutral_response.status if neutral_response is not None else None
            except Exception as exc:
                result["neutral_error"] = context.redact(f"{type(exc).__name__}: {exc}")

            try:
                response = page.goto(OZON_PRODUCT.format(sku=sku), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(7000)
                result["document_status"] = response.status if response is not None else None
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
                cookies = browser_context.cookies()
                result["cookie_count"] = len(cookies)
                result["cookie_names"] = sorted({str(item.get("name")) for item in cookies if item.get("name")})
                browser_context.storage_state(path=str(STORAGE_FILE))
                result["storage_state_saved_local"] = STORAGE_FILE.exists()
            except Exception:
                pass
            try:
                page.screenshot(path=str(SCREENSHOT_FILE), full_page=False)
                result["screenshot_saved_local"] = SCREENSHOT_FILE.exists()
            except Exception:
                pass

            browser_context.close()
            browser.close()
    except Exception as exc:
        result["browser_error"] = context.redact(f"{type(exc).__name__}: {exc}")

    binding_ok = curl_identity is not None and _same_identity(curl_identity, result.get("neutral_identity"))
    blocked = bool(result.get("network_denial_marker") or result.get("antibot_marker"))
    loaded = result.get("document_status") == 200 and not blocked

    if not neutral.ok or curl_identity is None:
        gate = "OZON_NATIVE_HEADED_PROXY_BINDING_FAILED"
    elif not binding_ok:
        gate = "OZON_NATIVE_HEADED_PROXY_BINDING_FAILED"
    elif result.get("entrypoint_observed"):
        gate = "OZON_NATIVE_HEADED_ENTRYPOINT_OBSERVED"
    elif blocked:
        gate = "OZON_NATIVE_HEADED_BLOCKED"
    elif loaded:
        gate = "OZON_NATIVE_HEADED_PAGE_LOADED_NO_ENTRYPOINT"
    else:
        gate = "OZON_NATIVE_HEADED_RUNTIME_FAILED"

    report = {
        "goal": "prove_normal_chromium_ozon_access_via_native_playwright_proxy",
        "proxy_context": context.safe_identity,
        "curl_neutral": {"transport": neutral.safe_dict(), "identity": curl_identity},
        "headed": result,
        "proxy_binding_same_identity": binding_ok,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Screenshot/storage state are local/Git-ignored. Cookie values and proxy credentials are not reported.")
    print(f"[EVIDENCE] {gate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
