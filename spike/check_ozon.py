"""Feasibility spike (part 2): read an Ozon price through a mobile proxy.

Ozon режет прокси по репутации IP. Резидентные/датацентровые адреса он метит как
VPN («нет соединения») или кидает капчу-пазл. Мобильные IP (MTS/Билайн/МегаФон/Tele2)
он почти не трогает. У ASocks мобильный пул отдаётся под липкой сессией
(`hold-session-session-<id>`), но за одним ASN-фильтром лежат вперемешку и мобильные,
и обычные операторы — какой попадётся, зависит от session-id.

Поэтому скрипт сам перебирает session-id (FIND_MOBILE=1): крутит идентификатор,
проверяет оператора на лёгком сайте, и как только ловит МОБИЛЬНЫЙ липкий IP —
на нём же идёт на Ozon и достаёт JSON с ценой.

Режимы (env):
    PROXY=host:port:user:pass   — прокси ASocks (user содержит hold-session/hold-query)
    PROXY_SCHEME=https          — по умолчанию (ASocks = TLS до прокси); http для CONNECT-прокси
    FIND_MOBILE=1               — автопоиск мобильного липкого IP, затем Ozon (главный режим)
    PROBE=1                     — один прогон: показать IP/оператора и выйти (без Ozon)
    MOBILE_TRIES=15             — сколько session-id перебрать в поиске мобильного
    HEADLESS=0                  — видимый браузер

Setup (Windows cmd):
    pip install playwright && python -m playwright install chromium
    set PROXY=host:port:user:pass
    set FIND_MOBILE=1
    python spike/check_ozon.py
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys

from playwright.sync_api import sync_playwright

PRODUCT_ID = "3129447770"
OZON_URL = f"https://www.ozon.ru/product/{PRODUCT_ID}/"
API_URL = (f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{PRODUCT_ID}/")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru']});
window.chrome={runtime:{}};
"""
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox",
               "--ignore-certificate-errors"]
MOBILE_ISP = ("mts", "vimpelcom", "beeline", "megafon", "tele2", "t2 mobile", "yota")


def parse_proxy() -> tuple[str, str, str, str | None, str | None]:
    scheme = (os.environ.get("PROXY_SCHEME", "https").strip() or "https")
    raw = os.environ.get("PROXY", "").strip()
    if not raw:
        sys.exit("ERROR: задай PROXY='host:port:user:pass'")
    p = raw.split(":")
    if len(p) == 4:
        return scheme, p[0], p[1], p[2], p[3]
    if len(p) == 2:
        return scheme, p[0], p[1], None, None
    sys.exit("ERROR: формат PROXY — host:port:user:pass")


def build_proxy(scheme: str, host: str, port: str,
                user: str | None, pw: str | None) -> dict[str, str]:
    d = {"server": f"{scheme}://{host}:{port}"}
    if user:
        d["username"], d["password"] = user, pw
    return d


def rotate_session(login: str, sid: str) -> str:
    """Подставить новый session-id (=новый липкий IP) в логин ASocks."""
    if "hold-query" in login:
        base = login.replace("hold-query", "").rstrip("-")
        return f"{base}-hold-session-session-{sid}"
    if "hold-session-session-" in login:
        return re.sub(r"hold-session-session-.*$", f"hold-session-session-{sid}", login)
    return f"{login}-hold-session-session-{sid}"


def is_mobile(isp: str | None) -> bool:
    low = (isp or "").lower()
    return any(k in low for k in MOBILE_ISP)


def new_page(pw, proxy, state_path: str | None = None, force_headless: bool = False):
    # MANUAL всегда в видимом браузере — иначе капчу не решить; пробы (force_headless) — скрытно.
    headless = True if force_headless else (
        os.environ.get("HEADLESS", "1") != "0" and os.environ.get("MANUAL") != "1")
    browser = pw.chromium.launch(headless=headless, proxy=proxy, args=LAUNCH_ARGS)
    kwargs = dict(user_agent=UA, locale="ru-RU", timezone_id="Europe/Moscow",
                  viewport={"width": 1366, "height": 900})
    if state_path and os.path.exists(state_path):
        kwargs["storage_state"] = state_path
        print(f"  (переиспользую куки из {os.path.basename(state_path)})")
    ctx = browser.new_context(**kwargs)
    ctx.add_init_script(STEALTH)
    # В ручном режиме НЕ режем картинки — иначе не видно капчу-пазл. В остальных режимах режем для скорости.
    if os.environ.get("MANUAL") != "1":
        ctx.route("**/*", lambda r: (
            r.abort() if r.request.resource_type in
            {"image", "media", "font", "stylesheet"} else r.continue_()))
    return browser, ctx, ctx.new_page()


def probe_ip(page) -> dict:
    page.goto("https://ipwho.is/", wait_until="commit", timeout=20000)
    page.wait_for_timeout(1200)
    return json.loads(page.inner_text("body"))


def find_price(api_text: str) -> None:
    data = json.loads(api_text)
    states = data.get("widgetStates", {})
    hit = False
    for key, val in states.items():
        if "webPrice" in key or "webSale" in key:
            try:
                p = json.loads(val)
            except Exception:  # noqa: BLE001
                continue
            print(f"    [{key.split('-')[0]}] цена: {p.get('price')}  "
                  f"без карты: {p.get('originalPrice') or p.get('cardPrice')}  "
                  f"с Ozon-картой: {p.get('cardPrice') or p.get('price')}")
            hit = True
    if not hit:
        print(f"    цена в JSON не найдена; ключи виджетов: {list(states)[:8]}")


def ozon_step(ctx, page, here: str) -> None:
    print("\n=== Ozon: антибот → JSON с ценой ===")
    dump_path = os.path.join(here, "ozon_api_dump.txt")
    state_path = os.path.join(here, "ozon_state.json")
    manual = os.environ.get("MANUAL") == "1"
    try:
        page.goto(OZON_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:  # noqa: BLE001
        print(f"  заход не завершился ({str(e).splitlines()[0]}) — продолжаю")
    if manual:
        print("  ┌─ РУЧНОЙ РЕЖИМ ─────────────────────────────────────────────")
        print("  │ В открывшемся окне Ozon реши капчу-пазл (двигай ползунок),")
        print("  │ дождись, пока загрузится карточка товара с ценой,")
        print("  │ затем вернись сюда в консоль и нажми Enter.")
        print("  └────────────────────────────────────────────────────────────")
        try:
            input("  >>> Enter после решения капчи... ")
        except EOFError:
            page.wait_for_timeout(30000)
    fetch_js = """async (url) => {
        const r = await fetch(url, {headers:{'x-o3-app-name':'dweb_client'}});
        return await r.text();
    }"""
    api_text = ""
    for attempt in range(1, 7):
        page.wait_for_timeout(0 if manual else 4000)
        try:
            api_text = page.evaluate(fetch_js, API_URL)
        except Exception as e:  # noqa: BLE001
            print(f"  попытка {attempt}: fetch ошибка {str(e).splitlines()[0]}")
            continue
        if (api_text or "").lstrip().startswith("{"):
            print(f"  попытка {attempt}: JSON получен ({len(api_text)} б)")
            break
        print(f"  попытка {attempt}: пока антибот ({len(api_text or '')} б) — перезагружаю")
        if manual:
            break
        try:
            page.reload(wait_until="domcontentloaded", timeout=45000)
        except Exception:  # noqa: BLE001
            pass
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write(api_text or "")
    if (api_text or "").lstrip().startswith("{"):
        find_price(api_text)
        ctx.storage_state(path=state_path)
        print(f"  → Ozon подтверждён. Куки сохранены: {state_path}")
        print("     Дальше замеры без капчи: set MANUAL= и set REUSE=1")
    else:
        print(f"  антибот не пройден. дамп: {dump_path}")
    page.screenshot(path=os.path.join(here, "ozon_debug.png"))


def main() -> None:
    scheme, host, port, user, pw = parse_proxy()
    here = os.path.dirname(os.path.abspath(__file__))
    find_mobile = os.environ.get("FIND_MOBILE") == "1"
    probe_only = os.environ.get("PROBE") == "1"
    tries = int(os.environ.get("MOBILE_TRIES", "15"))
    state_path = os.path.join(here, "ozon_state.json")
    reuse = os.environ.get("REUSE") == "1"

    with sync_playwright() as pw_ctx:
        # --- обычный/PROBE режим: как есть, без перебора ---
        if not find_mobile:
            proxy = build_proxy(scheme, host, port, user, pw)
            browser, ctx, page = new_page(pw_ctx, proxy, state_path if reuse else None)
            print("=== Шаг 0: браузер + прокси на лёгком сайте ===")
            try:
                info = probe_ip(page)
                print(f"  OK: IP {info.get('ip')}, город {info.get('city')}, "
                      f"оператор {(info.get('connection') or {}).get('isp')}")
            except Exception as e:  # noqa: BLE001
                print(f"  ПРОВАЛ на лёгком сайте: {str(e).splitlines()[0]}")
                browser.close()
                return
            if probe_only:
                print("  PROBE=1 — только проверка IP. Для автопоиска мобильного: set FIND_MOBILE=1")
                browser.close()
                return
            ozon_step(ctx, page, here)
            browser.close()
            return

        # --- FIND_MOBILE: перебираем session-id, ловим мобильный липкий IP ---
        if not user:
            sys.exit("ERROR: FIND_MOBILE требует логин с сессией (host:port:user:pass)")
        print(f"=== Автопоиск мобильного липкого IP (до {tries} попыток) ===")
        page = browser = None
        for attempt in range(1, tries + 1):
            sid = secrets.token_hex(4)
            proxy = build_proxy(scheme, host, port, rotate_session(user, sid), pw)
            browser, ctx, page = new_page(pw_ctx, proxy, force_headless=True)  # пробы — скрытно
            try:
                info = probe_ip(page)
            except Exception as e:  # noqa: BLE001
                print(f"  #{attempt} sid={sid}: провал ({str(e).splitlines()[0]})")
                browser.close()
                continue
            isp = (info.get("connection") or {}).get("isp")
            browser.close()
            if is_mobile(isp):
                print(f"  #{attempt} sid={sid}: IP {info.get('ip')}, {isp}  ← МОБИЛЬНЫЙ, берём")
                # перезапуск на этом же липком sid — уже с учётом MANUAL/HEADLESS
                browser, ctx, page = new_page(pw_ctx, proxy, state_path if reuse else None)
                ozon_step(ctx, page, here)
                browser.close()
                return
            print(f"  #{attempt} sid={sid}: IP {info.get('ip')}, {isp}  — не моб, меняю")
        print(f"  за {tries} попыток мобильный IP не выпал. Увеличь MOBILE_TRIES "
              f"или проверь, что у прокси выбран mobile-тип/оператор.")


if __name__ == "__main__":
    main()
