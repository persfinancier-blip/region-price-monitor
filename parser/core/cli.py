# -*- coding: utf-8 -*-
"""Интерактивный CLI (десктоп) — меню как в оригинале.

Поток: источник SKU → куда сохранять → проверка профилей →
       досоздание недостающего по регионам → добавление новых → парсинг.

Движок: Ozon скрытый curl_cffi/edge (цена из виджета webPrice), вилка 403 в браузер; WB API.
"""
import os
import sys
import json
import csv
import shutil
from pathlib import Path

import config
import ozon
import wb
import storage
import warm_browser
from db import ParserDB, wizard_connect

_PG_CACHE = None   # параметры PG, если SKU брали из БД — чтобы не спрашивать дважды


# ═══════════════════ проверки профилей ═══════════════════
def check_ozon_profile(profile_dir):
    cookie_file = Path(profile_dir) / "cookies.json"
    if not cookie_file.exists():
        return False, "Профиль не найден"
    try:
        from curl_cffi import requests as creq
        cookies = json.loads(cookie_file.read_text(encoding="utf-8"))
        s = creq.Session(impersonate="edge")
        for c in cookies:
            dom = c.get("domain", ".ozon.ru").lstrip(".")
            s.cookies.set(c["name"], c["value"], domain=dom, path=c.get("path", "/"))
        r = s.get("https://www.ozon.ru/", timeout=15)
        if r.status_code == 200:
            low = r.text.lower()
            if any(x in low for x in ["captcha", "капча", "проверка", "checking your browser"]):
                return False, "Капча/блокировка (куки протухли)"
            return True, "OK"
        if r.status_code == 403:
            return False, "HTTP 403 (куки протухли)"
        return False, f"HTTP {r.status_code}"
    except ImportError:
        return False, "curl_cffi не установлен"
    except Exception as e:
        return False, str(e)


def check_wb_dest(dest):
    if dest is None:
        return False, "dest не задан"
    try:
        import requests
        r = requests.get(config.WB_API_URL,
                         params={"appType": 1, "curr": "rub", "dest": dest, "spp": 30, "nm": "1"},
                         headers=config.WB_HEADERS, timeout=10)
        return (True, "API отвечает") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
    except Exception as e:
        return False, str(e)


def review_profiles(cfg):
    regions = cfg.get("regions", [])
    if not regions:
        return cfg

    print("\n" + "=" * 60)
    print("   🌍 Проверка существующих профилей")
    print("=" * 60)

    statuses = []
    for r in regions:
        code = r["code"]
        name = r.get("name", code)
        ozon_dir = r.get("ozon_profile_dir") or str(config.PROFILES_DIR / f"ozon_{code}")
        ozon_ok, ozon_msg = check_ozon_profile(ozon_dir)
        wb_ok, wb_msg = check_wb_dest(r.get("wb_dest"))
        print(f"\n   {code} — {name}")
        print(f"      Ozon: {'✅' if ozon_ok else '❌'} {ozon_msg}")
        print(f"      WB:   {'✅' if wb_ok else '❌'} {wb_msg}")
        statuses.append({"code": code, "ozon_ok": ozon_ok, "wb_ok": wb_ok, "region": r})

    bad = [s for s in statuses if not s["ozon_ok"] or not s["wb_ok"]]
    if not bad:
        print("\n   ✅ Все профили работают!")
        return cfg

    print(f"\n   ❌ Проблемные профили: {', '.join(s['code'] for s in bad)}")
    print("\n   Что делать?")
    print("   [1] Удалить ВСЕ нерабочие профили (оставить регионы в config)")
    print("   [2] Удалить ВСЕ регионы ПОЛНОСТЬЮ из config")
    print("   [1-<код>] Удалить нерабочие профили одного региона (например: 1-msk)")
    print("   [2-<код>] Удалить регион ПОЛНОСТЬЮ (например: 2-msk)")
    print("   [0] Ничего не удалять")
    ans = input("\n   Ответ: ").strip().lower()

    if not ans or ans == "0":
        return cfg

    mode, targets = None, set()
    if ans == "1":
        mode, targets = "profiles", {s["code"] for s in bad}
    elif ans == "2":
        mode, targets = "full", {s["code"] for s in bad}
    elif ans.startswith("1-"):
        mode, targets = "profiles", {ans[2:].strip()}
    elif ans.startswith("2-"):
        mode, targets = "full", {ans[2:].strip()}
    if not mode or not targets:
        print("   ⚠️ Неверный ввод, ничего не удалено.")
        return cfg

    for code in list(targets):
        region = next((r for r in regions if r["code"] == code), None)
        if not region:
            continue
        s = next((x for x in statuses if x["code"] == code), None)
        if mode == "profiles":
            if s and not s["ozon_ok"]:
                d = region.get("ozon_profile_dir") or str(config.PROFILES_DIR / f"ozon_{code}")
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                    print(f"   🗑️ Удалён Ozon: {d}")
                region.pop("ozon_profile_dir", None)
            if s and not s["wb_ok"]:
                wb_dir = str(config.PROFILES_DIR / f"wb_{code}")
                if os.path.exists(wb_dir):
                    shutil.rmtree(wb_dir, ignore_errors=True)
                region.pop("wb_dest", None)
        else:
            d = region.get("ozon_profile_dir") or str(config.PROFILES_DIR / f"ozon_{code}")
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
            wb_dir = str(config.PROFILES_DIR / f"wb_{code}")
            if os.path.exists(wb_dir):
                shutil.rmtree(wb_dir, ignore_errors=True)
            regions.remove(region)

    cfg["regions"] = regions
    config.save_config(cfg)
    print("   ✅ Готово.")
    return cfg


# ═══════════════════ источник SKU ═══════════════════
def _load_sku_from_file():
    print("\n📂 Укажите путь к файлу с товарами (CSV или Excel):")
    print("   Колонки: marketplace (wb/ozon), sku")
    sample = config.SAMPLE_SKU
    prompt = f"Путь (Enter = {sample}): " if sample.exists() else "Путь: "
    path = input(prompt).strip().strip('"')
    if not path and sample.exists():
        path = str(sample)
    if not path or not os.path.exists(path):
        print("❌ Файл не найден.")
        return None
    ext = os.path.splitext(path)[1].lower()
    products = {"wb": [], "ozon": []}
    try:
        if ext == ".csv":
            rows = list(csv.DictReader(open(path, encoding="utf-8")))
        elif ext in (".xlsx", ".xls"):
            import pandas as pd
            rows = pd.read_excel(path).to_dict("records")
        else:
            print("❌ Неподдерживаемый формат.")
            return None
    except Exception as e:
        print(f"❌ Ошибка чтения: {e}")
        return None
    for row in rows:
        low = {str(k).lower(): v for k, v in row.items()}
        mp = str(low.get("marketplace", "")).strip().lower()
        sku = str(low.get("sku", "")).strip()
        if mp in products and sku and sku.lower() != "nan":
            products[mp].append(sku)
    if "marketplace" not in {str(k).lower() for row in rows for k in row}:
        print("❌ Нужны колонки 'marketplace' и 'sku'.")
        return None
    config.PRODUCTS_PATH.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Загружено: WB={len(products['wb'])}, Ozon={len(products['ozon'])}")
    return products


def _load_sku_from_db():
    global _PG_CACHE
    params = wizard_connect()
    try:
        db = ParserDB.from_params(params)
        products = db.load_skus(active_only=True)
        _PG_CACHE = params
        total = sum(len(v) for v in products.values())
        print(f"✅ Из БД загружено: WB={len(products['wb'])}, Ozon={len(products['ozon'])}, всего={total}")
        config.PRODUCTS_PATH.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
        return products
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return None


def _load_sku_from_json():
    products = config.load_products()
    if not (products.get("wb") or products.get("ozon")):
        print("❌ products.json пуст.")
        return None
    print(f"✅ Из JSON: WB={len(products['wb'])}, Ozon={len(products['ozon'])}")
    return products


def load_sku_list():
    print("\n" + "─" * 50)
    print("   📥 Выбор источника SKU")
    print("─" * 50)
    print("   [1] 📁 Файл (CSV / Excel, колонки: marketplace, sku)")
    print("   [2] 🐘 PostgreSQL (таблица parser_skus, колонки: sku, marketplace)")
    print('   [3] 📄 products.json (структура: {"wb": ["sku1", ...], "ozon": ["sku2", ...]})')
    print("   [q] ❌ Выход")
    choice = input("\n   Выбор: ").strip().lower()
    if choice == "1":
        return _load_sku_from_file()
    if choice == "2":
        return _load_sku_from_db()
    if choice == "3":
        return _load_sku_from_json()
    if choice == "q":
        sys.exit(0)
    print("❌ Неверный выбор.")
    return None


# ═══════════════════ куда сохранять ═══════════════════
def choose_output():
    global _PG_CACHE
    print("\n" + "─" * 50)
    print("   📤 Куда сохранять результаты")
    print("─" * 50)
    print("   [1] 📁 Папка (CSV, колонки: sku, marketplace, region_code, price, ...)")
    print("   [2] 🐘 PostgreSQL (таблица parser_results)")
    print("   [3] 📁 + 🐘 Оба варианта")
    print("   [q] ❌ Выход")
    choice = input("\n   Выбор: ").strip().lower()
    out = {"folder": None, "pg": None}
    if choice == "1":
        out["folder"] = input("   Папка (по умолчанию results): ").strip() or str(config.RESULTS_DIR)
    elif choice == "2":
        out["pg"] = _PG_CACHE or wizard_connect()
    elif choice == "3":
        out["folder"] = input("   Папка (по умолчанию results): ").strip() or str(config.RESULTS_DIR)
        out["pg"] = _PG_CACHE or wizard_connect()
    elif choice == "q":
        sys.exit(0)
    else:
        print("❌ Неверный выбор, используем папку 'results'")
        out["folder"] = str(config.RESULTS_DIR)
    return out


# ═══════════════════ регионы ═══════════════════
def _ozon_alive(region):
    d = region.get("ozon_profile_dir")
    return bool(d) and (Path(d) / "cookies.json").exists()


def repair_regions(products, regions):
    """Досоздаём ТОЛЬКО недостающее (мёртвый/отсутствующий профиль), авто-переход по списку."""
    sample_ozon = (products.get("ozon") or [None])[0]
    sample_wb = (products.get("wb") or [None])[0]
    for region in regions:
        code = region["code"]
        name = region.get("name", code)
        need_ozon = bool(products.get("ozon")) and not _ozon_alive(region)
        need_wb = bool(products.get("wb")) and region.get("wb_dest") is None
        if not need_ozon and not need_wb:
            continue
        print(f"\n   🔄 Регион '{code}' — досоздаём недостающее...")
        if need_ozon and sample_ozon:
            prof = warm_browser.warm_region(code, sample_ozon, name)
            if prof:
                region["ozon_profile_dir"] = prof
        if need_wb and sample_wb:
            dest = warm_browser.get_wb_dest(code, sample_wb)
            if dest is not None:
                region["wb_dest"] = dest
        config.save_config({"regions": regions})
        print(f"✅ Регион '{code}' готов (dest={region.get('wb_dest')})")
    return regions


def add_new_regions(products, regions):
    sample_ozon = (products.get("ozon") or [None])[0]
    sample_wb = (products.get("wb") or [None])[0]
    first = True
    while True:
        q = "\n🆕 Добавить новые регионы? (да/нет): " if first else "Добавить ещё? (да/нет): "
        if input(q).strip().lower() != "да":
            break
        first = False
        code = input("\nКод региона (например, msk): ").strip()
        if not code:
            continue
        if any(r["code"] == code for r in regions):
            print(f"   ⚠️ Регион '{code}' уже есть.")
            continue
        name = input("Название региона (например, Москва): ").strip() or code
        region = {"code": code, "name": name}
        if sample_ozon:
            prof = warm_browser.warm_region(code, sample_ozon, name)
            if prof:
                region["ozon_profile_dir"] = prof
        if sample_wb:
            dest = warm_browser.get_wb_dest(code, sample_wb)
            if dest is None:
                m = input("   Введите dest вручную (или Enter для пропуска): ").strip()
                if m.lstrip("-").isdigit():
                    dest = int(m)
            if dest is not None:
                region["wb_dest"] = dest
        regions.append(region)
        config.save_config({"regions": regions})
        print(f"✅ Регион '{code}' готов (dest={region.get('wb_dest')})")
    return regions


# ═══════════════════ сохранение ═══════════════════
def save_results(results, output_cfg):
    if not results:
        return
    code = results[0].get("region_code", "")
    if output_cfg.get("folder"):
        for mp in ("ozon", "wb"):
            rows = [r for r in results if r.get("marketplace") == mp]
            if rows:
                storage.save_csv(rows, code, mp, output_cfg["folder"])
    if output_cfg.get("pg"):
        try:
            ParserDB.from_params(output_cfg["pg"]).save_results(results)
        except Exception as e:
            print(f"   ⚠️ Ошибка сохранения в БД: {e}")


# ═══════════════════ парсинг ═══════════════════
def run_parsing(products, regions, output_cfg):
    print("\n🚀 Запуск парсинга...")
    for region in regions:
        code = region["code"]
        proxy = region.get("proxy")

        # Ozon
        if products.get("ozon"):
            ozon_profile = region.get("ozon_profile_dir") or str(config.PROFILES_DIR / f"ozon_{code}")
            cookies = ozon.load_cookies(ozon_profile)
            if cookies:
                ozon_results, failed = [], []
                for i, sku in enumerate(products["ozon"]):
                    print(f"   Ozon {sku} (регион {code})...", end=" ")
                    res = ozon.fetch_price(sku, cookies, proxy=proxy, save_debug=(i == 0))
                    if "price" in res:
                        res["marketplace"] = "ozon"
                        res["region_code"] = code
                        ozon_results.append(res)
                        print("OK")
                    else:
                        failed.append(sku)
                        print("❌")
                if failed:
                    print(f"\n      ↪ curl_cffi не справился с {len(failed)} SKU, открываю браузер...")
                    for r in warm_browser.browser_fetch_prices(code, failed):
                        r["marketplace"] = "ozon"
                        r["region_code"] = code
                        ozon_results.append(r)
                if ozon_results:
                    save_results(ozon_results, output_cfg)
                    print(f"   Ozon: сохранено {len(ozon_results)} цен")
            else:
                print(f"   ⚠️ Ozon профиль отсутствует для региона {code}, пропускаем")

        # WB
        dest = region.get("wb_dest")
        if products.get("wb") and dest is not None:
            print(f"   WB batch {len(products['wb'])} SKU (регион {code})...", end=" ")
            wb_results = wb.fetch_prices_batch(products["wb"], dest, proxy)
            for r in wb_results:
                r["marketplace"] = "wb"
                r["region_code"] = code
            if wb_results:
                save_results(wb_results, output_cfg)
                print(f"OK — сохранено {len(wb_results)} цен")
            else:
                print("❌")
        elif products.get("wb"):
            print(f"   ⚠️ WB dest не задан для региона {code}, пропускаем")

    print("✅ Готово!")


# ═══════════════════ main ═══════════════════
def main():
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 20 + "🛒  ПАРСЕР WB/OZON" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")

    products = load_sku_list()
    if products is None or not (products.get("wb") or products.get("ozon")):
        sys.exit(1)

    output_cfg = choose_output()

    cfg = config.load_config()
    cfg = review_profiles(cfg)
    regions = cfg.get("regions", [])

    regions = repair_regions(products, regions)
    regions = add_new_regions(products, regions)

    if not regions:
        print("❌ Нет регионов для парсинга.")
        sys.exit(1)

    run_parsing(products, regions, output_cfg)


if __name__ == "__main__":
    main()
