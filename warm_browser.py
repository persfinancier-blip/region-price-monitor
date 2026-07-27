# -*- coding: utf-8 -*-
"""Прогрев кук Ozon — ДЕСКТОП (видимый браузер, логин + ПВЗ + карточка).
Нужен экран: на headless-сервере не запускать. Импортирует uc лениво.

Флоу (по дизайну): свежий профиль -> логин + ПВЗ -> карточка ->
авто-детект: капча -> ждём решения; увидел цену -> авто-закрытие.
"""
import json
import time
import shutil
from pathlib import Path

from config import PROFILES_DIR
from platform_utils import kill_browser, kill_pid_tree, get_chrome_major_version

POLL_TIMEOUT = 180

PRICE_JS = r"""
let w = document.querySelector('[data-widget="webPrice"]') ||
        document.querySelector('[data-widget="webSale"]');
if (w) { let m = w.innerText.match(/([\d\s   ]+)\s*₽/); if (m) return m[1].replace(/\D/g,''); }
return null;
"""


def _profile_dir(region_code):
    return PROFILES_DIR / f"ozon_{region_code}"


def wipe_profile(region_code):
    kill_browser()
    p = _profile_dir(region_code)
    for _ in range(3):
        if not p.exists():
            return
        try:
            shutil.rmtree(p); return
        except Exception:
            time.sleep(1); kill_browser()


def _new_driver(profile_dir):
    import undetected_chromedriver as uc
    kill_browser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    o = uc.ChromeOptions()
    o.add_argument(f"--user-data-dir={profile_dir}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_argument("--no-sandbox")
    ver = get_chrome_major_version()
    d = uc.Chrome(options=o, version_main=ver) if ver else uc.Chrome(options=o)
    d.set_window_size(1500, 950)
    return d


def _detect(driver):
    title = (driver.title or "").lower()
    if any(x in title for x in ["antibot", "captcha", "капч", "проверк", "challenge"]):
        return "captcha", None
    try:
        val = driver.execute_script(PRICE_JS)
    except Exception:
        val = None
    if val and val.isdigit() and int(val) > 0:
        return "price", float(val)
    return "loading", None


def _wait_card(driver, sku, label=""):
    print(f"   📦 {label}карточка {sku} — смотри в окно браузера...")
    driver.get(f"https://www.ozon.ru/product/{sku}/")
    warned = False
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        state, price = _detect(driver)
        if state == "price":
            print(f"   ✅ вижу цену: {price} ₽ — закрываю окно")
            return price
        if state == "captcha" and not warned:
            print("   🧩 КАПЧА — реши её в окне браузера, дальше сам продолжу...")
            warned = True
        time.sleep(2)
    print("   ⏱️ не дождался цены (таймаут).")
    return None


def warm_region(region_code, sample_sku, region_name=None):
    """Возвращает путь к профилю с cookies.json, или None."""
    label = region_name or region_code
    wipe_profile(region_code)                      # всегда свежий профиль
    profile = _profile_dir(region_code)
    driver = _new_driver(profile)
    pid = getattr(driver, "browser_pid", None)
    ok_price = None
    try:
        driver.get("https://www.ozon.ru")
        time.sleep(3)
        print(f"\n  🌍 Регион {label}. Свежий профиль.")
        print("   • ЗАЛОГИНЬСЯ в Ozon (важно — залогиненного не гоняют через капчу).")
        print("   • Выбери/подтверди точку получения (ПВЗ).")
        input("   Enter, когда готов...")
        ok_price = _wait_card(driver, sample_sku, label="прогрев: ")
        cookies = driver.get_cookies()
        (profile / "cookies.json").write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        names = {c.get("name", "") for c in cookies}
        print(f"   💾 куки: {len(cookies)} | залогинен: {'__Secure-access-token' in names}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        kill_pid_tree(pid)
        print("   🌐 окно закрыто")
    return str(profile) if ok_price else None
