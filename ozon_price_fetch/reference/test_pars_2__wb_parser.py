import requests
from decimal import Decimal

def fetch_price(sku, dest, proxy=None):
    url = "https://card.wb.ru/cards/v4/detail"
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": dest,
        "spp": 30,
        "nm": sku
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    products = data.get("products")
    if not products:
        return None
    product = products[0]
    sizes = product.get("sizes")
    if not sizes:
        return None
    price_obj = sizes[0].get("price")
    if not price_obj:
        return None
    price = Decimal(str(price_obj.get("product", 0))) / 100
    price_base = Decimal(str(price_obj.get("basic", 0))) / 100
    return {
        "sku": sku,
        "price": float(price),
        "price_base": float(price_base),
        "currency": "RUB",
        "is_available": price > 0,
        "raw": product
    }
