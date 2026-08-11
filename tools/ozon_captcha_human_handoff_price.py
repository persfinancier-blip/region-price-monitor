from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge
from mobile_proxy import _parse_combined_proxy, find_mobile_proxy
from platform_utils import get_chrome_major_version, kill_pid_tree
from probe_ozon_single_run_c23 import _selected_context
from probe_ozon_solver_robustness_c24 import _obtain_challenge

DEFAULT_SKU = "3129447770"
PRICE_JS = r"""
let w = document.querySelector('[data-widget="webPrice"]') ||
        document.querySelector('[data-widget="webSale"]');
if (!w) return null;
let m = w.innerText.match(/([\d\s   ]+)\s*₽/);
if (!m) return null;
return m[1].replace(/\D/g,'');
"""


def _new_driver(proxy_url: str, profile_dir: Path):
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--proxy-server={proxy_url}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")

    version = get_chrome_major_version()
    driver = uc.Chrome(options=options, version_main=version) if version else uc.Chrome(options=options)
    driver.set_window_size(1500, 950)
    return driver


def _read_dom_price(driver) -> float | None:
    try:
        value = driver.execute_script(PRICE_JS)
    except Exception:
        return None
    if value and str(value).isdigit() and int(value) > 0:
        return float(value)
    return None


def main() -> int:
    print("=== Ozon human CAPTCHA handoff -> price ===")
    print("Challenge opens in visible Chrome on SAME sticky proxy.")
    print("You solve the CAPTCHA manually once; script then continues to price.")

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        print(f"[ERROR] PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-human-handoff",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        print(f"[EVIDENCE] OZON_HANDOFF_MOBILE_PROXY_BLOCKED gate={selector.get('gate')}")
        return 8

    context, session_id, selected_ip = _selected_context(
        proxy_server, proxy_user, proxy_password, selected
    )
    print(f"SAME STICKY: {selected.get('operator')} / {selected_ip}")

    challenge, challenge_url, strategy, attempts, data_access = _obtain_challenge(context, sku)
    if data_access is not None and data_access.get("ok"):
        print(f"PRICE: {data_access.get('price')} RUB")
        print("[EVIDENCE] OZON_PRICE_WITHOUT_CHALLENGE_PROVEN")
        return 0

    if not challenge_url:
        print("[EVIDENCE] OZON_HANDOFF_CHALLENGE_NOT_OBTAINED")
        return 8

    driver = None
    pid = None
    try:
        with tempfile.TemporaryDirectory(prefix="rpm_ozon_handoff_") as tmp:
            profile_dir = Path(tmp)
            with LocalBrowserProxyBridge(context) as bridge:
                driver = _new_driver(bridge.proxy_url, profile_dir)
                pid = getattr(driver, "browser_pid", None)

                print("\nOpening Ozon CAPTCHA in visible Chrome...")
                driver.get(challenge_url)
                print("Solve the slider in the browser. After Ozon accepts it, press Enter here.")
                input("Enter after CAPTCHA is accepted: ")

                driver.get(f"https://www.ozon.ru/product/{sku}/")
                deadline = time.time() + 90
                while time.time() < deadline:
                    price = _read_dom_price(driver)
                    if price is not None:
                        print(f"\nPRICE: {price} RUB")
                        print("[EVIDENCE] OZON_PRICE_AFTER_HUMAN_CAPTCHA_PROVEN")
                        return 0
                    time.sleep(2)

                print("[EVIDENCE] OZON_HANDOFF_PRICE_NOT_FOUND_AFTER_CAPTCHA")
                return 8
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        kill_pid_tree(pid)


if __name__ == "__main__":
    raise SystemExit(main())
