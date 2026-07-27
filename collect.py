# -*- coding: utf-8 -*-
"""СБОР ЦЕН (headless) — работает на Linux-сервере.
Ozon: скрытый curl_cffi/edge по кукам (прогретым на десктопе).
WB:   прямой API. Выход: PG (если задан в окружении) и/или CSV.

Прогрев здесь НЕ делается (нужен видимый браузер). Если Ozon отдаёт 403 —
куки протухли: перепрогреть на десктопе и обновить cookies.json.

Запуск:
    python collect.py            # источник/приёмник по конфигу и окружению
    python collect.py --csv      # форсировать CSV
    python collect.py --no-db    # не писать в PG
"""
import sys
import argparse
from pathlib import Path

import config
import ozon
import wb
import storage


def _enrich(results, marketplace, region_code):
    out = []
    for r in results:
        if "error" in r:
            continue
        r = dict(r)
        r["marketplace"] = marketplace
        r["region_code"] = region_code
        out.append(r)
    return out


def get_products(db):
    if db is not None:
        try:
            return db.load_skus(active_only=True)
        except Exception as e:
            print(f"⚠️ PG load_skus: {e}; беру products.json")
    return config.load_products()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help="писать CSV")
    ap.add_argument("--no-db", action="store_true", help="не писать в PG")
    args = ap.parse_args()

    cfg = config.load_config()
    regions = cfg.get("regions", [])
    if not regions:
        print("❌ Нет регионов в config.json. Настрой на десктопе (cli.py).")
        sys.exit(1)

    # PG — из окружения (сервер)
    db = None
    pg = config.pg_params_from_env()
    if pg and not args.no_db:
        try:
            from db import ParserDB
            db = ParserDB.from_params(pg)
            print(f"🐘 PG: {pg['host']}:{pg['port']}/{pg['dbname']}")
        except Exception as e:
            print(f"⚠️ PG недоступен ({e}); пишу CSV.")
            db = None
    write_csv = args.csv or db is None

    products = get_products(db)
    all_results = []
    stale = []

    for region in regions:
        code = region["code"]
        name = region.get("name", code)
        proxy = region.get("proxy")
        print(f"\n▶ Регион {code} ({name})")

        # ── Ozon (скрытый) ──
        ozon_profile = region.get("ozon_profile_dir") or str(config.PROFILES_DIR / f"ozon_{code}")
        cookies = ozon.load_cookies(ozon_profile)
        ozon_results = []
        if products.get("ozon") and cookies:
            for i, sku in enumerate(products["ozon"]):
                print(f"   Ozon {sku}...")
                res = ozon.fetch_price(sku, cookies, proxy=proxy, save_debug=(i == 0))
                if "error" in res:
                    if res["error"] == "403":
                        stale.append((code, sku))
                    print(f"      ❌ {res['error']}")
                else:
                    ozon_results.append(res)
                    print(f"      ✅ {res['price']} ₽ (карта {res.get('price_card')}, обычная {res.get('price_regular')})")
        elif products.get("ozon"):
            print(f"   ⚠️ нет cookies.json для {code} — перепрогрей на десктопе.")

        ozon_results = _enrich(ozon_results, "ozon", code)

        # ── WB (API) ──
        wb_results = []
        dest = region.get("wb_dest")
        if products.get("wb") and dest:
            print(f"   WB batch {len(products['wb'])} SKU...")
            wb_results = _enrich(wb.fetch_prices_batch(products["wb"], dest, proxy), "wb", code)
        elif products.get("wb"):
            print(f"   ⚠️ нет wb_dest для {code}")

        region_results = ozon_results + wb_results
        all_results.extend(region_results)

        if write_csv:
            if ozon_results:
                storage.save_csv(ozon_results, code, "ozon")
            if wb_results:
                storage.save_csv(wb_results, code, "wb")

    # запись в PG
    run_id = None
    if db is not None and all_results:
        run_id = db.save_results(all_results)
        print(f"\n💾 PG: сохранено {len(all_results)} строк (run_id={run_id})")

    print("\n" + "=" * 56)
    print(f"  ИТОГ: {len(all_results)} цен | CSV={'да' if write_csv else 'нет'} | PG={'да' if db else 'нет'}")
    if stale:
        print(f"  ⚠️ Ozon 403 (протухли куки, нужен перепрогрев): {len(stale)} — {stale}")
    print("=" * 56)
    return all_results


if __name__ == "__main__":
    main()
