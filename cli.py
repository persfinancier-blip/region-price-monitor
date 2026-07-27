# -*- coding: utf-8 -*-
"""Интерактивный CLI (ДЕСКТОП) — простой, в стиле старого парсера.
Прогрев регионов + запуск сбора + управление SKU. Сервер запускает collect.py напрямую.
"""
import sys
import csv
from pathlib import Path

import config
import collect


def banner():
    print("\n" + "=" * 56)
    print("        🛒  ПАРСЕР ЦЕН WB / OZON  (десктоп)")
    print("=" * 56)


def show_regions(cfg):
    regions = cfg.get("regions", [])
    if not regions:
        print("   (регионов нет)")
        return
    for r in regions:
        prof = Path(config.PROFILES_DIR / f"ozon_{r['code']}" / "cookies.json")
        ck = "куки есть" if prof.exists() else "нет кук"
        print(f"   • {r['code']} ({r.get('name', r['code'])}) | wb_dest={r.get('wb_dest')} | {ck}")


def add_region(cfg):
    code = input("   Код региона (напр. msk): ").strip()
    if not code:
        return
    name = input("   Название (напр. Москва): ").strip() or code
    dest = input("   WB dest (число, Enter — пропустить): ").strip()
    region = {"code": code, "name": name}
    if dest:
        try:
            region["wb_dest"] = int(dest)
        except ValueError:
            print("   ⚠️ dest не число, пропущен")
    regions = [r for r in cfg.get("regions", []) if r["code"] != code]
    regions.append(region)
    cfg["regions"] = regions
    config.save_config(cfg)
    print(f"   ✅ регион {code} сохранён")


def import_sku():
    path = input("   Путь к CSV (колонки marketplace,sku): ").strip()
    if not path or not Path(path).exists():
        print("   ❌ файл не найден")
        return
    products = {"wb": [], "ozon": []}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mp = (row.get("marketplace") or "").strip().lower()
            sku = (row.get("sku") or "").strip()
            if mp in products and sku:
                products[mp].append(sku)
    config.PRODUCTS_PATH.write_text(
        __import__("json").dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ WB={len(products['wb'])}, Ozon={len(products['ozon'])} → products.json")


def warm_regions(cfg):
    try:
        import warm_browser
    except Exception as e:
        print(f"   ❌ прогрев требует браузерных зависимостей: {e}")
        return
    products = config.load_products()
    sample = (products.get("ozon") or ["1964684436"])[0]
    for r in cfg.get("regions", []):
        if input(f"   Прогреть {r['code']}? (y/n): ").strip().lower() == "y":
            warm_browser.warm_region(r["code"], sample, r.get("name"))


def main():
    cfg = config.load_config()
    while True:
        banner()
        show_regions(cfg)
        print("\n   [1] 🔥 Прогреть регионы (браузер, логин+ПВЗ)")
        print("   [2] ▶  Собрать цены сейчас (скрытый режим)")
        print("   [3] ➕ Добавить/обновить регион")
        print("   [4] 📥 Импорт SKU из CSV")
        print("   [q] выход")
        ch = input("\n   Выбор: ").strip().lower()
        if ch == "1":
            cfg = config.load_config()
            warm_regions(cfg)
        elif ch == "2":
            sys.argv = ["collect.py", "--csv"]
            collect.main()
            input("\n   Enter, чтобы продолжить...")
        elif ch == "3":
            add_region(cfg); cfg = config.load_config()
        elif ch == "4":
            import_sku()
        elif ch == "q":
            break


if __name__ == "__main__":
    main()
