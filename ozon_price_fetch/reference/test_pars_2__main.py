from utils import load_json, save_results_csv
from wb_parser import fetch_price as wb_fetch
from ozon_parser import fetch_price as ozon_fetch

def collect_all():
    print("▶ Загрузка config.json...")
    config = load_json("config.json")
    print("▶ Загрузка products.json...")
    products = load_json("products.json")
    regions = config.get("regions", [])
    print(f"▶ Найдено регионов: {len(regions)}")

    for region in regions:
        code = region["code"]
        print(f"▶ Обработка региона {code}")
        proxy = region.get("proxy")

        # WB
        wb_sku_list = products.get("wb", [])
        print(f"   WB товаров: {len(wb_sku_list)}")
        wb_results = []
        for sku in wb_sku_list:
            dest = region.get("wb_dest")
            if not dest:
                continue
            print(f"   Запрос WB: {sku} dest={dest}")
            res = wb_fetch(sku, dest, proxy)
            if res:
                wb_results.append(res)
                print(f"      Цена: {res['price']}")
            else:
                print(f"      ❌ Не удалось получить цену")
        if wb_results:
            print(f"   WB: получено {len(wb_results)} результатов, сохранено")
            save_results_csv(wb_results, code, "wb")
        else:
            print(f"   WB: результатов нет")

        # Ozon
        ozon_sku_list = products.get("ozon", [])
        print(f"   Ozon товаров: {len(ozon_sku_list)}")
        ozon_results = []
        for sku in ozon_sku_list:
            cookie_file = region.get("ozon_cookie_file")
            if not cookie_file:
                continue
            print(f"   Запрос Ozon: {sku} cookie={cookie_file}")
            res = ozon_fetch(sku, cookie_file, code, proxy)
            if res:
                ozon_results.append(res)
                print(f"      Цена: {res['price']}")
            else:
                print(f"      ❌ Не удалось получить цену")
        if ozon_results:
            print(f"   Ozon: получено {len(ozon_results)} результатов, сохранено")
            save_results_csv(ozon_results, code, "ozon")
        else:
            print(f"   Ozon: результатов нет")

    print("✅ Готово")

if __name__ == "__main__":
    collect_all()