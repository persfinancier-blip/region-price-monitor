"""Feasibility spike: read region-specific prices through a proxy.

Throwaway. Not production code. Proves the risky mechanisms only:
  1. proxy gives a Russian regional exit IP;
  2. price of a specific SKU is readable;
  3. price/delivery differs by region.

Run (Windows cmd):
    set PROXY=host:port:user:pass
    python spike/check_price.py

Никаких секретов в файле: строка прокси берётся из переменной окружения PROXY.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse

import requests

# --- образцовый SKU (дан владельцем) ---
WB_NM = 629760017
OZON_URL = "https://www.ozon.ru/product/3129447770/"

# города: координаты -> WB geo вернёт корректный dest; запасной dest на случай сбоя гео
CITIES = {
    "Москва": {"coords": (55.7558, 37.6173), "fallback_dest": -1257786},
    "Владивосток": {"coords": (43.1155, 131.8855), "fallback_dest": 123589350},
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
WB_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate",  # без brotli — requests его не декодирует
    "Origin": "https://www.wildberries.ru",
    "Referer": f"https://www.wildberries.ru/catalog/{WB_NM}/detail.aspx",
}


def build_proxies() -> dict[str, str]:
    raw = os.environ.get("PROXY", "").strip()
    if not raw:
        sys.exit("ERROR: задай переменную окружения PROXY='host:port:user:pass'")
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        url = f"http://{urllib.parse.quote(user)}:{urllib.parse.quote(pwd)}@{host}:{port}"
    elif len(parts) == 2:
        url = f"http://{parts[0]}:{parts[1]}"
    else:
        sys.exit("ERROR: формат PROXY — host:port:user:pass или host:port")
    return {"http": url, "https": url}


def proxy_geo(proxies: dict[str, str]) -> None:
    print("=== 1. Что показывает прокси (гео выходного IP, по HTTPS) ===")
    try:
        r = requests.get("https://ipwho.is/", headers={"User-Agent": UA},
                         proxies=proxies, timeout=30)
        d = r.json()
        conn = d.get("connection", {}) or {}
        print(f"  IP: {d.get('ip')}  город: {d.get('city')}  регион: {d.get('region')}  "
              f"страна: {d.get('country')}  оператор: {conn.get('isp') or conn.get('org')}")
    except Exception as e:  # noqa: BLE001
        print(f"  НЕ УДАЛОСЬ определить IP через прокси: {e}")


def wb_dest(proxies: dict[str, str], lat: float, lon: float) -> int | None:
    url = ("https://user-geo-data.wildberries.ru/get-geo-info"
           f"?currency=RUB&latitude={lat}&longitude={lon}&locale=ru")
    try:
        r = requests.get(url, headers=WB_HEADERS, proxies=proxies, timeout=30)
        data = r.json()
        print(f"    [гео raw] {json.dumps(data, ensure_ascii=False)[:300]}")
        # ищем dest в разных возможных местах
        for key in ("destWithPrefix", "dest"):
            if data.get(key) is not None:
                return int(str(data[key]).split(";")[-1].split(",")[-1])
        xinfo = data.get("xinfo", "")
        if "dest=" in xinfo:
            return int(xinfo.split("dest=")[1].split("&")[0])
    except Exception as e:  # noqa: BLE001
        print(f"    (гео не отдал dest: {e})")
    return None


def wb_price(proxies: dict[str, str], dest: int) -> None:
    base = f"appType=1&curr=rub&dest={dest}&spp=30&nm={WB_NM}"
    candidates = [
        f"https://card.wb.ru/cards/v2/detail?{base}",
        f"https://card.wb.ru/cards/v4/detail?{base}",
        f"https://card.wb.ru/cards/v1/detail?{base}",
        f"https://u-card.wb.ru/cards/v2/detail?{base}",
        f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest={dest}&nm={WB_NM}",
    ]
    prod = None
    for url in candidates:
        try:
            r = requests.get(url, headers=WB_HEADERS, proxies=proxies, timeout=30)
        except Exception as e:  # noqa: BLE001
            print(f"    [{url.split('?')[0]}] сеть: {e}")
            continue
        body = r.text.strip()
        tag = url.split('.ru')[0].split('//')[1] + url.split('/cards')[1].split('?')[0]
        print(f"    [{tag}] HTTP {r.status_code}, {len(body)} байт")
        if r.status_code == 200 and body:
            try:
                j = r.json()
                products = (j.get("data") or j).get("products")
                prod = products[0]
                break
            except Exception as e:  # noqa: BLE001
                print(f"      не разобрал: {e}: {body[:120]!r}")
    if prod is None:
        print("    → ни один эндпоинт не отдал цену")
        return
    size = prod["sizes"][0]
    price = size.get("price", {}) or {}
    print(f"    [цена raw] {json.dumps(price, ensure_ascii=False)}")
    basic = price.get("basic", 0) / 100
    product = price.get("product", 0) / 100
    total = price.get("total", price.get("product", 0)) / 100
    wallet = round(total * 0.98, 2)  # WB-кошелёк ~ -2% от итоговой, ориентировочно
    print(f"    базовая: {basic:.2f}  со скидкой: {product:.2f}  "
          f"итог: {total:.2f}  с WB-кошельком (~): {wallet:.2f}")
    print(f"    доставка time1/time2: {prod.get('time1')}/{prod.get('time2')} ч")


def wb_block(proxies: dict[str, str]) -> None:
    print("\n=== 2. WB — nmId", WB_NM, "по регионам ===")
    for city, cfg in CITIES.items():
        print(f"  [{city}]")
        dest = wb_dest(proxies, *cfg["coords"]) or cfg["fallback_dest"]
        print(f"    dest={dest}")
        try:
            wb_price(proxies, int(dest))
        except Exception as e:  # noqa: BLE001
            print(f"    ОШИБКА чтения цены WB: {e}")


def ozon_block(proxies: dict[str, str]) -> None:
    print("\n=== 3. Ozon (ожидаем антибот у голого запроса) ===")
    try:
        r = requests.get(OZON_URL, headers={"User-Agent": UA}, proxies=proxies, timeout=30)
        blocked = r.status_code != 200 or "captcha" in r.text.lower() or len(r.text) < 5000
        verdict = ("ПОХОЖЕ НА БЛОК/КАПЧУ — нужен headless-браузер"
                   if blocked else "страница пришла")
        print(f"    HTTP {r.status_code}, размер {len(r.text)} байт → {verdict}")
    except Exception as e:  # noqa: BLE001
        print(f"    ОШИБКА: {e}")


def main() -> None:
    proxies = build_proxies()
    proxy_geo(proxies)
    wb_block(proxies)
    ozon_block(proxies)
    print("\nИтог: если WB показал разные цены/доставку по городам, а Ozon упирается в антибот — "
          "механика подтверждена (WB — через API, Ozon — через Playwright).")


if __name__ == "__main__":
    main()
