from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge
from platform_utils import get_chrome_major_version
from transport import ProxyContext, ProxyContextError

NEUTRAL_URL = "https://api.i.pn/json/"
DEFAULT_WB_SKU = "629760017"
DEFAULT_OZON_SKU = "3129447770"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "browser_visibility_report.json"


def _parse_identity(text: str) -> dict[str, Any] | None:
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


def _browser_fetch_text(driver: Any, url: str) -> dict[str, Any]:
    """Fetch from inside Chrome so JSON-viewer DOM cannot hide the raw response."""
    script = """
const url = arguments[0];
const done = arguments[arguments.length - 1];
fetch(url, {cache: 'no-store', credentials: 'omit'})
  .then(async (response) => {
    const text = await response.text();
    done({ok: response.ok, status: response.status, text: text, error: null});
  })
  .catch((error) => done({ok: false, status: null, text: '', error: String(error)}));
"""
    try:
        result = driver.execute_async_script(script, url)
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "text": "",
            "error": f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
        }
    if not isinstance(result, dict):
        return {"ok": False, "status": None, "text": "", "error": "unexpected fetch result"}
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "text": str(result.get("text") or ""),
        "error": result.get("error"),
    }


def _snapshot(driver: Any, requested_url: str, navigation_error: str | None) -> dict[str, Any]:
    try:
        current_url = driver.current_url or ""
    except Exception:
        current_url = ""
    try:
        title = driver.title or ""
    except Exception:
        title = ""
    try:
        ready_state = driver.execute_script("return document.readyState")
    except Exception:
        ready_state = None
    try:
        body_text = driver.find_element("tag name", "body").text or ""
    except Exception:
        body_text = ""
    return {
        "requested_url": requested_url,
        "current_url": current_url,
        "title": title[:300],
        "ready_state": ready_state,
        "body_text_chars": len(body_text),
        "navigation_error": navigation_error,
    }


def _navigate(driver: Any, url: str) -> dict[str, Any]:
    error = None
    try:
        driver.get(url)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return _snapshot(driver, url, error)


def _save_screenshot(driver: Any, filename: str) -> dict[str, Any]:
    path = LOCAL_PROBES / filename
    try:
        ok = bool(driver.save_screenshot(str(path)))
    except Exception as exc:
        return {
            "saved": False,
            "local_file": str(path),
            "error": f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
        }
    return {"saved": ok, "local_file": str(path)}


def main() -> int:
    print("=== WB/Ozon visible browser smoke ===")
    print("Goal: only prove that real marketplace pages are visible through the configured proxy.")
    print("No price/API/endpoint parsing is performed in this run.")

    city = input("City label: ").strip() or "city"
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    wb_sku = input(f"WB SKU [Enter = {DEFAULT_WB_SKU}]: ").strip() or DEFAULT_WB_SKU
    ozon_sku = input(f"Ozon SKU [Enter = {DEFAULT_OZON_SKU}]: ").strip() or DEFAULT_OZON_SKU

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

    report: dict[str, Any] = {
        "goal": "visible_marketplace_pages_only",
        "proxy_context": context.safe_identity,
        "browser": None,
        "wb": None,
        "ozon": None,
    }

    profile_dir = Path(tempfile.mkdtemp(prefix="rpm_visible_browser_", dir=str(LOCAL_PROBES)))
    driver: Any = None
    try:
        with LocalBrowserProxyBridge(context) as bridge:
            try:
                import undetected_chromedriver as uc

                options = uc.ChromeOptions()
                options.add_argument(f"--user-data-dir={profile_dir}")
                options.add_argument(f"--proxy-server={bridge.proxy_url}")
                options.add_argument("--start-maximized")
                options.add_argument("--disable-quic")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-background-networking")
                options.add_argument("--disable-component-update")
                options.add_argument("--disable-sync")
                options.add_argument("--no-first-run")
                options.add_argument("--no-default-browser-check")
                version = get_chrome_major_version()
                driver = (
                    uc.Chrome(options=options, version_main=version)
                    if version
                    else uc.Chrome(options=options)
                )
                driver.set_page_load_timeout(45)
                driver.set_script_timeout(30)
            except Exception as exc:
                report["browser"] = {
                    "started": False,
                    "error": context.redact(f"{type(exc).__name__}: {exc}"),
                    "proxy_bridge": bridge.safe_state,
                }
                REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False, indent=2))
                print(f"[FAIL] BROWSER_STARTUP_FAILED; report: {REPORT_FILE}")
                return 3

            # Prove that the visible Chrome itself is bound to the proxy before opening marketplaces.
            # Chrome may render application/json in its own viewer, so read the raw response with a
            # same-browser fetch rather than trusting DOM body.text.
            neutral = _navigate(driver, NEUTRAL_URL)
            neutral_fetch = _browser_fetch_text(driver, NEUTRAL_URL)
            identity = _parse_identity(neutral_fetch.get("text") or "")
            report["browser"] = {
                "started": True,
                "visible": True,
                "proxy_bridge": bridge.safe_state,
                "neutral": neutral,
                "neutral_fetch": {
                    "ok": neutral_fetch.get("ok"),
                    "status": neutral_fetch.get("status"),
                    "error": neutral_fetch.get("error"),
                },
                "egress_identity": identity,
            }
            if not identity or not identity.get("query") or not identity.get("city"):
                report["browser"]["gate"] = "BROWSER_PROXY_BINDING_UNPROVEN"
                REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False, indent=2))
                input("Browser proxy binding is unproven. Press Enter to close Chrome...")
                return 4

            report["browser"]["gate"] = "BROWSER_PROXY_BINDING_CONFIRMED"
            print(
                f"[OK] Browser egress: {identity.get('city')} / {identity.get('query')} "
                f"mobile={identity.get('mobile')}"
            )

            wb_url = f"https://www.wildberries.ru/catalog/{wb_sku}/detail.aspx"
            print(f"[OPEN] WB: {wb_url}")
            report["wb"] = _navigate(driver, wb_url)
            report["wb"]["screenshot"] = _save_screenshot(driver, "browser_visibility_wb.png")

            try:
                driver.switch_to.new_window("tab")
            except Exception as exc:
                report["ozon"] = {
                    "requested_url": f"https://www.ozon.ru/product/{ozon_sku}/",
                    "tab_error": context.redact(f"{type(exc).__name__}: {exc}"),
                }
            else:
                ozon_url = f"https://www.ozon.ru/product/{ozon_sku}/"
                print(f"[OPEN] Ozon: {ozon_url}")
                report["ozon"] = _navigate(driver, ozon_url)
                report["ozon"]["screenshot"] = _save_screenshot(driver, "browser_visibility_ozon.png")

            REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("\n=== SAFE REPORT ===")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print("\nInspect both visible browser tabs now.")
            print("Local screenshots were saved under parser/core/local/probes for direct visual evidence.")
            print("We only care whether the real WB and Ozon pages are visibly usable.")
            input("Press Enter when you are done looking at the pages; Chrome will then close...")
            return 0
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
