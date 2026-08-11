from __future__ import annotations

import json
from pathlib import Path
import sys

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
    _body_text,
    _safe_identity,
    _same_identity,
    _run_browser_mode,
)

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_browser_access_c13_report.json"
HEADLESS_SCREENSHOT = LOCAL_PROBES / "ozon_browser_access_c13_headless.png"
HEADED_SCREENSHOT = LOCAL_PROBES / "ozon_browser_access_c13_headed.png"


def _blocked(result: dict) -> bool:
    return bool(result.get("network_denial_marker") or result.get("antibot_marker"))


def main() -> int:
    print("=== Ozon browser access gate C13 ===")
    print("ONE ProxyContext. Compare headless and normal Chromium with zero user interaction.")
    print("Do NOT click, type or solve captcha if a browser window appears.")

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
        headless = _run_browser_mode(p, context, sku, headless=True, screenshot=HEADLESS_SCREENSHOT)
        headed = _run_browser_mode(p, context, sku, headless=False, screenshot=HEADED_SCREENSHOT)

    binding_ok = (
        neutral_identity is not None
        and _same_identity(neutral_identity, headless.get("neutral_identity"))
        and _same_identity(neutral_identity, headed.get("neutral_identity"))
    )
    headless_blocked = _blocked(headless)
    headed_blocked = _blocked(headed)
    headless_entrypoint = bool(headless.get("entrypoint_observed"))
    headed_entrypoint = bool(headed.get("entrypoint_observed"))

    if not binding_ok:
        gate = "OZON_BROWSER_PROXY_BINDING_UNPROVEN"
    elif headless_entrypoint:
        gate = "OZON_ENTRYPOINT_OBSERVED_HEADLESS"
    elif headless_blocked and headed_entrypoint:
        gate = "OZON_HEADLESS_SPECIFIC_BLOCK_EVIDENCED"
    elif headless_blocked and not headed_blocked:
        gate = "OZON_HEADLESS_SPECIFIC_BLOCK_EVIDENCED"
    elif headless_blocked and headed_blocked:
        gate = "OZON_BLOCKED_BOTH_BROWSER_MODES"
    elif headed_entrypoint:
        gate = "OZON_ENTRYPOINT_OBSERVED_HEADED"
    else:
        gate = "OZON_ACCESS_DISCRIMINATOR_INCONCLUSIVE"

    report = {
        "goal": "prove_whether_real_chromium_can_load_ozon_without_user_interaction",
        "proxy_context": context.safe_identity,
        "curl_neutral": {"transport": neutral.safe_dict(), "identity": neutral_identity},
        "headless": headless,
        "headed": headed,
        "proxy_binding_same_identity_all_modes": binding_ok,
        "headless_blocked": headless_blocked,
        "headed_blocked": headed_blocked,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Screenshots are local/Git-ignored. Do not interact with any Ozon challenge.")
    print(f"[EVIDENCE] {gate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
