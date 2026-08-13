import json
from curl_cffi import requests
from decimal import Decimal

def fetch_price(sku, cookie_file, region_code, proxy=None):
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies_data = json.load(f)
            if isinstance(cookies_data, list):
                cookies = {c["name"]: c["value"] for c in cookies_data}
            else:
                cookies = cookies_data
            print(f"   Загружены куки (первые 5): {list(cookies.keys())[:5]}")
    except Exception as e:
        print(f"   Ошибка загрузки кук: {e}")
        return None

    url = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
    params = {"url": f"/product/{sku}/"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Content-Type": "application/json",
        "x-o3-app-name": "dweb_client",
        "x-o3-app-version": "release_24-6-2026_e801a3c6",
        "x-o3-manifest-version": "frontend-ozon-ru:e801a3c62f8cfe341954419adfaa354dbaadf626,search-render-api:26877a5f1f6b92f5ef5a217ade8a0b151a885ecf,checkout-render-api:aecd1b3959ca8606f0af760c8123d37b48cc83e3,fav-render-api:59a97bd983119f6dddc92804adb6bad00256ce1b,pdp-render-api:c21f15997cdd645d082b0ef09089ca47e19990b7,sf-render-api:6b9533d13dc9cafbc4e33224af37432d468c316c",
        "x-o3-parent-requestid": "125632cc9bd414df409fc2ccea0ad3d2",
        "x-page-view-id": "4945465d-9e19-4c2b-6253-701e01b3ce2f",
        "Referer": f"https://www.ozon.ru/product/{sku}/"
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = requests.get(url, params=params, headers=headers, cookies=cookies, impersonate="chrome", proxies=proxies, timeout=15)
        print(f"   Ozon статус: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   Тело ответа (первые 300 символов): {resp.text[:300]}")
            return None
        data = resp.json()
        # Парсим цену из widgetStates
        widget_states = data.get("widgetStates", {})
        for key, value in widget_states.items():
            if "webPrice" in key or "webSale" in key:
                try:
                    parsed = json.loads(value) if isinstance(value, str) else value
                    price = parsed.get("price")
                    if price:
                        # Убираем лишние символы и конвертируем в Decimal
                        price_clean = price.replace("₽", "").replace(" ", "").replace(",", ".")
                        price_num = Decimal(price_clean)
                        return {
                            "sku": sku,
                            "price": float(price_num),
                            "price_base": float(price_num),
                            "currency": "RUB",
                            "is_available": True,
                            "raw": parsed
                        }
                except:
                    continue
        print("   ❌ Цена не найдена в ответе")
        return None
    except Exception as e:
        print(f"   Ошибка: {e}")
        return None