# -*- coding: utf-8 -*-
"""Ozon (скрытый режим, headless — работает на сервере).

Цена берётся СТРОГО из виджета webPrice запрошенного товара (JSON в HTML),
а не общим поиском ₽ (тот хватал чужие цены — рекомендации/рассрочку).
API у Ozon нет — запрос идёт на HTML страницы товара, цена внутри неё.
Импортирует только curl_cffi (без браузера) → безопасно на Linux-сервере.
"""
import re
import json

from config import OZON_STRATEGIES, DEBUG_DIR


def _num(t):
    if t is None:
        return None
    c = re.sub(r"[^\d.,]", "", str(t)).replace(" ", "").replace(",", ".")
    try:
        v = float(c)
        return v if v > 0 else None
    except Exception:
        return None


def parse_price(html):
    """Цена нужного SKU из состояния виджета webPrice (он на странице один)."""
    m = re.search(r'id="state-webPrice-[^"]*"\s+data-state=\'([^\']*)\'', html)
    if not m:
        return None
    try:
        st = json.loads(m.group(1))
    except Exception:
        return None
    card = _num(st.get("cardPrice"))
    reg = _num(st.get("price"))
    orig = _num(st.get("originalPrice"))
    price = card or reg
    if not price:
        return None
    return {
        "price": price,               # основная (по Ozon-карте)
        "price_card": card,
        "price_regular": reg,
        "price_original": orig,
        "price_base": orig or reg,    # «было» для совместимости со схемой
        "currency": "RUB",
        "is_available": bool(st.get("isAvailable", True)),
        "source": "webPrice-state",
    }


def fetch_price(sku, cookies_list, proxy=None, save_debug=False):
    """Тихий curl_cffi/edge по кукам. Возвращает dict цены, или {'error': '403'|'200_no_price'}."""
    from curl_cffi import requests as creq  # импорт здесь: не нужен, пока не парсим
    proxies = {"https": proxy, "http": proxy} if proxy else None
    url = f"https://www.ozon.ru/product/{sku}/"
    for imp, use_session in OZON_STRATEGIES:
        try:
            if use_session:
                s = creq.Session(impersonate=imp)
                for c in cookies_list:
                    dom = c.get("domain", ".ozon.ru").lstrip(".")
                    s.cookies.set(c["name"], c["value"], domain=dom, path=c.get("path", "/"))
                s.get("https://www.ozon.ru/", proxies=proxies, timeout=15)
                r = s.get(url, proxies=proxies, timeout=30)
            else:
                cd = {c["name"]: c["value"] for c in cookies_list}
                creq.get("https://www.ozon.ru/", cookies=cd, impersonate=imp, proxies=proxies, timeout=15)
                r = creq.get(url, cookies=cd, impersonate=imp, proxies=proxies, timeout=30)
            print(f"      [Ozon curl_cffi/edge/{'session' if use_session else 'dict'}] HTTP {r.status_code}")
            if r.status_code == 200:
                if save_debug:
                    (DEBUG_DIR / f"ozon_200_{sku}.html").write_text(r.text, encoding="utf-8")
                res = parse_price(r.text)
                if res:
                    res["sku"] = sku
                    return res
                return {"sku": sku, "error": "200_no_price"}
        except Exception as e:
            print(f"      [Ozon {imp}] {e}")
    return {"sku": sku, "error": "403"}


def load_cookies(profile_dir):
    from pathlib import Path
    ck = Path(profile_dir) / "cookies.json"
    if not ck.exists():
        return None
    return json.loads(ck.read_text(encoding="utf-8"))
