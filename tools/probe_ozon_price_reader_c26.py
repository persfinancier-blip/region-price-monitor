from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import config
import ozon
from mobile_proxy import _parse_combined_proxy, find_mobile_proxy
from probe_ozon_single_run_c23 import _selected_context

DEFAULT_SKU = "3129447770"


def _profiles() -> list[Path]:
    root = config.PROFILES_DIR
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "cookies.json").exists()
    )


def _choose_legacy_profile() -> Path | None:
    profiles = _profiles()
    print("\nSG04 did not return a price.")
    answer = input("Run EXPLICIT SG05 authenticated legacy fallback? [y/N]: ").strip().lower()
    if answer not in {"y", "yes", "д", "да"}:
        return None

    if profiles:
        print("Local profiles with cookies.json:")
        for index, path in enumerate(profiles, 1):
            print(f"  [{index}] {path}")
        raw = input("Profile number, or paste profile directory: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(profiles):
            return profiles[int(raw) - 1]
        if raw:
            return Path(raw)
    else:
        raw = input("Paste authenticated Ozon profile directory: ").strip()
        if raw:
            return Path(raw)
    return None


def main() -> int:
    print("=== Ozon assembled price reader C26 ===")
    print("SG04 proxy-first -> PRICE/CHALLENGE; SG05 only by explicit operator choice.")
    print("NO CAPTCHA submission. NO automatic fallback.")
    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        print(f"[ERROR] PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    print("[1/3] Selecting fresh mobile sticky session ...")
    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-c26",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        print(f"[EVIDENCE] OZON_PRICE_READER_MOBILE_PROXY_BLOCKED gate={selector.get('gate')}")
        return 8

    context, session_id, selected_ip = _selected_context(
        proxy_server, proxy_user, proxy_password, selected
    )
    print(f"[2/3] SG04 primary through {selected.get('operator')} / {selected_ip} ...")
    primary = ozon.fetch_price_proxy_first(sku, context)
    status = primary.get("status")
    if status == "price":
        print(
            f"PRICE: {primary['price']} {primary.get('currency', 'RUB')} "
            f"(card={primary.get('price_card')} regular={primary.get('price_regular')})"
        )
        print("[EVIDENCE] OZON_PRICE_PRIMARY_PROVEN")
        return 0

    print(f"SG04 RESULT: {status}")
    if status == "challenge":
        print("Ozon returned a typed CHALLENGE; no fake price was produced.")
    else:
        print(f"detail={primary.get('error') or primary.get('transport_error')}")

    profile = _choose_legacy_profile()
    if profile is None:
        print("[EVIDENCE] OZON_PRICE_PRIMARY_BLOCKED_FALLBACK_NOT_INVOKED")
        return 8

    print(f"[3/3] Explicit SG05 authenticated legacy fallback: {profile}")
    cookies = ozon.load_cookies(profile)
    legacy = ozon.fetch_price_legacy_authenticated(sku, cookies, proxy=None, save_debug=False)
    if legacy.get("status") == "price":
        print(
            f"PRICE: {legacy['price']} {legacy.get('currency', 'RUB')} "
            f"(card={legacy.get('price_card')} regular={legacy.get('price_regular')})"
        )
        print("[EVIDENCE] OZON_PRICE_EXPLICIT_LEGACY_FALLBACK_PROVEN")
        return 0

    print(f"SG05 RESULT: {legacy.get('status')} error={legacy.get('error')}")
    print("[EVIDENCE] OZON_PRICE_EXPLICIT_LEGACY_FALLBACK_FAILED")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
