# -*- coding: utf-8 -*-
"""Прогрев кук по всем регионам из config.json (ДЕСКТОП, браузер).
После прогрева cookies.json лежат в profiles/ozon_<код>/ — их и копируют на сервер.

Запуск:  python warm.py            (все регионы)
         python warm.py msk kzn    (только указанные)
"""
import sys

import config
import warm_browser


def main():
    cfg = config.load_config()
    regions = cfg.get("regions", [])
    products = config.load_products()
    sample = products.get("ozon", ["1964684436"])
    sample_sku = sample[0] if sample else "1964684436"

    only = set(sys.argv[1:])
    todo = [r for r in regions if not only or r["code"] in only]
    if not todo:
        print("❌ Нет регионов для прогрева (проверь config.json).")
        return

    print(f"🔥 Прогрев регионов: {[r['code'] for r in todo]}")
    for r in todo:
        prof = warm_browser.warm_region(r["code"], sample_sku, r.get("name"))
        if prof:
            print(f"✅ {r['code']}: {prof}")
        else:
            print(f"❌ {r['code']}: прогрев не подтверждён")
    print("\nГотово. Скопируй папку profiles/ на сервер (или запусти collect.py локально).")


if __name__ == "__main__":
    main()
