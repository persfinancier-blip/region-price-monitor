from __future__ import annotations

import argparse
import json
import os
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


def _append_profile(found: dict[str, Path], path: Path | str | None) -> None:
    if not path:
        return
    try:
        candidate = Path(path).expanduser()
    except Exception:
        return
    if (candidate / "cookies.json").exists():
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        found[key] = candidate


def _profiles_from_root(found: dict[str, Path], root: Path) -> None:
    if not root.exists() or not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if path.is_dir():
            _append_profile(found, path)


def _profiles_from_config(found: dict[str, Path], core_dir: Path) -> None:
    cfg_path = core_dir / "config.json"
    if not cfg_path.exists():
        return
    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return
    for region in payload.get("regions", []) if isinstance(payload, dict) else []:
        if not isinstance(region, dict):
            continue
        raw = region.get("ozon_profile_dir")
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = core_dir / candidate
        _append_profile(found, candidate)


def _profiles() -> list[Path]:
    found: dict[str, Path] = {}

    # Current G01 runtime-local profiles.
    _profiles_from_root(found, config.PROFILES_DIR)
    _profiles_from_config(found, CORE)

    # Optional explicit legacy location without changing/copying secrets.
    env_profile = os.getenv("RPM_LEGACY_OZON_PROFILE")
    _append_profile(found, env_profile)

    # Preserved legacy checkout locations used by this project on Windows.
    legacy_cores = [
        Path(r"C:\DEV\region-price-monitor\parser\core"),
        Path(r"C:\Dev\region-price-monitor\parser\core"),
        ROOT.parent / "region-price-monitor" / "parser" / "core",
    ]
    for core_dir in legacy_cores:
        _profiles_from_root(found, core_dir / "profiles")
        _profiles_from_config(found, core_dir)

    return sorted(found.values(), key=lambda p: str(p).lower())


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--legacy-on-challenge",
        action="store_true",
        help=(
            "Explicitly authorize SG05 authenticated legacy fallback for this invocation "
            "if SG04 returns challenge/no-price."
        ),
    )
    return parser.parse_args()


def _try_legacy_profiles(sku: str) -> dict:
    profiles = _profiles()
    if not profiles:
        return {
            "status": "legacy_profile_missing",
            "error": "no authenticated Ozon profile with cookies.json was found",
        }

    print(f"[3/3] Trying {len(profiles)} preserved authenticated Ozon profile(s) ...")
    failures: list[dict] = []
    for index, profile in enumerate(profiles, 1):
        print(f"      profile {index}/{len(profiles)}: {profile}")
        cookies = ozon.load_cookies(profile)
        legacy = ozon.fetch_price_legacy_authenticated(
            sku,
            cookies,
            proxy=None,
            save_debug=False,
        )
        if legacy.get("status") == "price":
            legacy = dict(legacy)
            legacy["legacy_profile"] = str(profile)
            return legacy
        failures.append({
            "profile": str(profile),
            "status": legacy.get("status"),
            "error": legacy.get("error"),
        })

    return {
        "status": "legacy_profiles_failed",
        "error": "all discovered authenticated Ozon profiles failed",
        "failures": failures,
    }


def main() -> int:
    args = _args()
    print("=== Ozon assembled price reader C26 ===")
    if args.legacy_on_challenge:
        print("GOAL: SHOW OZON PRICE. SG05 authenticated fallback is explicitly authorized by this runner.")
    else:
        print("SG04 proxy-first -> PRICE/CHALLENGE; SG05 only by explicit operator choice.")
    print("NO CAPTCHA submission.")

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

    if not args.legacy_on_challenge:
        print("[EVIDENCE] OZON_PRICE_PRIMARY_BLOCKED_FALLBACK_NOT_INVOKED")
        return 8

    legacy = _try_legacy_profiles(sku)
    if legacy.get("status") == "price":
        print(
            f"PRICE: {legacy['price']} {legacy.get('currency', 'RUB')} "
            f"(card={legacy.get('price_card')} regular={legacy.get('price_regular')})"
        )
        print("[EVIDENCE] OZON_PRICE_EXPLICIT_LEGACY_FALLBACK_PROVEN")
        return 0

    print(f"SG05 RESULT: {legacy.get('status')} error={legacy.get('error')}")
    for failure in legacy.get("failures", []):
        print(
            f"      failed profile: {failure.get('profile')} "
            f"status={failure.get('status')} error={failure.get('error')}"
        )
    print("[EVIDENCE] OZON_PRICE_EXPLICIT_LEGACY_FALLBACK_FAILED")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
