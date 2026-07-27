# -*- coding: utf-8 -*-
"""Wildberries: прямой batch-API (без браузера). Проверенный рабочий путь."""
import time
from decimal import Decimal

import requests

from config import WB_API_URL, WB_HEADERS


def fetch_prices_batch(skus, dest, proxy=None, max_retries=3):
    """Возвращает список результатов по SKU для региона dest."""
    if not skus:
        return []
    params = {
        "appType": 1, "curr": "rub", "dest": dest, "spp": 30,
        "nm": ";".join(str(s) for s in skus),
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(max_retries):
        try:
            r = requests.get(WB_API_URL, params=params, headers=WB_HEADERS, proxies=proxies, timeout=15)
            print(f"      [WB] HTTP {r.status_code}")
            if r.status_code == 429:
                time.sleep(2 ** attempt + 1)
                continue
            if r.status_code != 200:
                return []
            data = r.json()
            raw = data.get("data")
            products = raw.get("products") if isinstance(raw, dict) else data.get("products")
            results = []
            for p in (products or []):
                sku = str(p.get("id"))
                sizes = p.get("sizes") or []
                if not sizes:
                    continue
                price_obj = sizes[0].get("price") or {}
                price = Decimal(str(price_obj.get("product", 0))) / 100
                base = Decimal(str(price_obj.get("basic", 0))) / 100
                results.append({
                    "sku": sku, "price": float(price), "price_base": float(base),
                    "currency": "RUB", "is_available": price > 0, "source": "wb-api",
                })
            return results
        except Exception as e:
            print(f"      [WB] ошибка: {e}")
            time.sleep(1)
    return []
