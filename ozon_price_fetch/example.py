"""Минимальный пример: цены нескольких товаров Ozon. Без браузера, без вопросов.

Разово подготовь куки:
    python cookies_from_curl.py --out cookies/ozon/msk.json
"""

from ozon_price import fetch_prices, save_csv

COOKIES = "cookies/ozon/msk.json"
PROXY = None  # или "1.2.3.4:8000:user:pass" — тот же, где снимались куки
SKUS = ["1964684436"]

results = fetch_prices(SKUS, cookie_file=COOKIES, proxy=PROXY, pause=1.5, debug_dir="debug")

for r in results:
    if "error" in r:
        print(f"{r['sku']}: {r['error']} — {r['message']}")
        continue
    card = f", с картой {r['price_card']}" if r["price_card"] else ""
    print(f"{r['sku']}: {r['price']} ₽ (без скидки {r['price_base']}{card})")

path = save_csv(results, "results", region="msk")
if path:
    print(f"CSV: {path}")
