from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Iterable, Sequence
from dotenv import load_dotenv
import mp_utils

load_dotenv()

DB_CONFIG = {
    "host": os.getenv('pg_host'),
    "port": os.getenv('db_port'), 
    "database": os.getenv('db_name'),
    "user": os.getenv('pg_user'),
    "password": os.getenv('pg_password'),
    "connect_timeout": 10
}

GEO_URL = "https://user-geo-data.wildberries.ru/get-geo-info"

CARD_ENDPOINTS = (
    "https://www.wildberries.ru/__internal/u-card/cards/v4/detail",
)

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en-US;q=0.7",
    "Referer": "https://www.wildberries.ru/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}

INTERNAL_HEADERS = {
    "accept": "*/*",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en-US;q=0.7",
    "priority": "u=1, i",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"iOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
    ),
    "x-requested-with": "XMLHttpRequest",
    "x-spa-version": "14.20.4",
}

INTERNAL_PARAMS = {
    "hide_vflags": "4294967296",
    "hide_dtype": "15",
    "mtype": "257",
    "lang": "ru",
    "ab_testing": "false",
}

BATCH_SIZE = 50
WALLET_DISCOUNT = 0.02

WB_TOKEN_REQUIRED = 498

_internal_disabled = False


class WbError(RuntimeError):
    """Не удалось получить данные WB."""


# ──────────────────────────────────────────────────────────────
# Работа с БД через mp_utils
# ──────────────────────────────────────────────────────────────

def load_cities(conn: Any, table_name: str) -> dict[str, dict[str, Any]]:
    conn = mp_utils.get_db_connection(DB_CONFIG, conn)
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0].lower() for desc in cursor.description]
        rows = cursor.fetchall()

    def find_col(candidates: list[str]) -> int | None:
        for c in candidates:
            if c in columns:
                return columns.index(c)
        return None

    i_code = find_col(["code", "city_code", "city"])
    i_name = find_col(["name", "city_name"])
    i_lat = find_col(["lat", "latitude"])
    i_lon = find_col(["lon", "longitude", "lng"])
    i_dest = find_col(["dest"])
    i_active = find_col(["is_active", "active"])

    if i_code is None or i_lat is None or i_lon is None:
        raise RuntimeError(f"В таблице {table_name} не найдены обязательные колонки (code/city, lat, lon). Доступные: {columns}")

    cities: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = str(r[i_code]).strip()
        if not code:
            continue
        if i_active is not None and r[i_active] is not None:
            val = r[i_active]
            if isinstance(val, int) and val == 0:
                continue
            if isinstance(val, bool) and not val:
                continue

        cities[code] = {
            "name": str(r[i_name]) if i_name is not None and r[i_name] is not None else code,
            "lat": float(r[i_lat]),
            "lon": float(r[i_lon]),
            "dest": int(r[i_dest]) if i_dest is not None and r[i_dest] is not None else None,
        }
    return cities


def load_target_skus(conn: Any, table_name: str, target_client_key: str | None = None) -> dict[str, list[str]]:
    conn = mp_utils.get_db_connection(DB_CONFIG, conn)
    with conn.cursor() as cursor:
        query = f"SELECT client_key, nm_id, is_active FROM {table_name}"
        params = []
        if target_client_key:
            query += " WHERE client_key = %s"
            params.append(target_client_key)
        cursor.execute(query, params)
        columns = [desc[0].lower() for desc in cursor.description]
        rows = cursor.fetchall()

    i_client = columns.index("client_key")
    i_nm = columns.index("nm_id")
    i_active = columns.index("is_active") if "is_active" in columns else None

    client_skus: dict[str, list[str]] = {}
    for r in rows:
        if i_active is not None and r[i_active] is not None:
            val = r[i_active]
            if isinstance(val, bool) and not val:
                continue
            if isinstance(val, int) and val == 0:
                continue

        ck = str(r[i_client]).strip()
        sku = str(r[i_nm] or "").strip()
        if not ck or not sku.isdigit():
            continue
        client_skus.setdefault(ck, []).append(sku)

    for ck in client_skus:
        client_skus[ck] = list(dict.fromkeys(client_skus[ck]))
    return client_skus


def save_results(conn: Any, table_name: str, client_key: str, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    conn = mp_utils.get_db_connection(DB_CONFIG, conn)
    
    sql = f"""
        INSERT INTO {table_name} (
            collected_date, client_key, nm_id, city_code, city_name, dest,
            price, price_base, price_wallet_est, total_qty, wh_count,
            wh_main, wh_main_qty, delivery_hours, is_available,
            supplier_name, rating, raw_stocks
        ) VALUES (
            CURRENT_DATE, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        ) ON CONFLICT (collected_date, client_key, nm_id, city_code) 
        DO UPDATE SET 
            collected_at = CURRENT_TIMESTAMP,
            price = EXCLUDED.price,
            price_base = EXCLUDED.price_base,
            price_wallet_est = EXCLUDED.price_wallet_est,
            total_qty = EXCLUDED.total_qty,
            wh_count = EXCLUDED.wh_count,
            wh_main = EXCLUDED.wh_main,
            wh_main_qty = EXCLUDED.wh_main_qty,
            delivery_hours = EXCLUDED.delivery_hours,
            is_available = EXCLUDED.is_available,
            supplier_name = EXCLUDED.supplier_name,
            rating = EXCLUDED.rating,
            raw_stocks = EXCLUDED.raw_stocks;
    """

    count = 0
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(sql, (
                client_key,
                int(row["sku"]) if str(row.get("sku", "")).isdigit() else 0,
                row.get("city"),
                row.get("city_name"),
                row.get("dest"),
                row.get("price"),
                row.get("price_base"),
                row.get("price_wallet_est"),
                int(row.get("qty") or 0),
                row.get("wh_count"),
                row.get("wh_main"),
                row.get("wh_main_qty"),
                row.get("delivery_h"),
                row.get("is_available", False),
                row.get("supplier"),
                row.get("rating"),
                json.dumps(row.get("_stocks", []))
            ))
            count += 1
    return count


# ──────────────────────────────────────────────────────────────
# Гео и запросы к WB
# ──────────────────────────────────────────────────────────────

def resolve_dest(
    code: str,
    city: dict[str, Any],
    *,
    proxies: dict[str, str] | None = None,
    timeout: int = 20,
) -> int:
    import requests

    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "address": city.get("address") or city["name"],
        "currency": "RUB",
        "locale": "ru",
    }
    response = requests.get(GEO_URL, params=params, headers=HEADERS, proxies=proxies, timeout=timeout)
    if response.status_code != 200:
        raise WbError(f"гео-API вернул HTTP {response.status_code} для города {code}")

    try:
        payload = response.json()
    except Exception as exc:
        raise WbError(f"гео-API вернул не JSON для города {code}") from exc

    dest = None
    xinfo = str(payload.get("xinfo") or "")
    match = re.search(r"dest=(-?\d+)", xinfo)
    if match:
        dest = int(match.group(1))
    else:
        for key in ("dest", "destId", "dest_id"):
            if payload.get(key) is not None:
                try:
                    dest = int(payload[key])
                    break
                except (TypeError, ValueError):
                    continue

    if dest is None:
        raise WbError(f"в ответе гео-API нет dest для города {code}: ключи {sorted(payload)[:10]}")

    return dest


def parse_proxy(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    raw = raw.strip()
    if "://" in raw:
        url = raw
    else:
        parts = raw.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            url = f"http://{user}:{password}@{host}:{port}"
        elif len(parts) == 2:
            url = f"http://{parts[0]}:{parts[1]}"
        else:
            raise SystemExit(f"Не понимаю формат прокси: {raw!r}")
    return {"http": url, "https": url}


def _kopecks(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value) / 100
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def collect_stocks(product: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    total = 0
    for size in product.get("sizes") or []:
        size_name = size.get("origName") or size.get("name") or ""
        for stock in size.get("stocks") or []:
            try:
                qty = int(stock.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                continue
            total += qty
            rows.append({
                "wh": stock.get("wh"),
                "qty": qty,
                "size": size_name,
                "dtype": stock.get("dtype"),
                "delivery_h1": stock.get("time1"),
                "delivery_h2": stock.get("time2"),
            })
    return total, rows


def parse_products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("data")
    products = raw.get("products") if isinstance(raw, dict) else payload.get("products")
    if not products:
        return []

    rows: list[dict[str, Any]] = []
    for product in products:
        sku = str(product.get("id") or product.get("nmId") or "")
        sizes = product.get("sizes") or []
        price_obj: dict[str, Any] = {}
        for size in sizes:
            candidate = size.get("price") or {}
            if candidate.get("product") or candidate.get("total"):
                price_obj = candidate
                break
        if not price_obj and sizes:
            price_obj = sizes[0].get("price") or {}

        price = _kopecks(price_obj.get("product")) or _kopecks(price_obj.get("total"))
        base = _kopecks(price_obj.get("basic"))
        total_price = _kopecks(price_obj.get("total"))

        qty, stock_rows = collect_stocks(product)
        if qty == 0:
            try:
                qty = int(product.get("totalQuantity") or 0)
            except (TypeError, ValueError):
                qty = 0

        warehouses = sorted({r["wh"] for r in stock_rows if r.get("wh") is not None})
        biggest = max(stock_rows, key=lambda r: r["qty"], default=None)
        delivery = [r["delivery_h1"] for r in stock_rows if isinstance(r.get("delivery_h1"), int)]

        rows.append({
            "sku": sku,
            "name": product.get("name"),
            "brand": product.get("brand"),
            "price": price,
            "price_base": base,
            "price_total": total_price,
            "price_wallet_est": round(price * (1 - WALLET_DISCOUNT), 2) if price else None,
            "currency": "RUB",
            "qty": qty,
            "wh_count": len(warehouses),
            "wh_main": biggest["wh"] if biggest else None,
            "wh_main_qty": biggest["qty"] if biggest else None,
            "delivery_h": min(delivery) if delivery else None,
            "is_available": bool(price) and qty > 0,
            "supplier": product.get("supplier"),
            "rating": product.get("reviewRating") or product.get("rating"),
            "_stocks": stock_rows,
        })
    return rows


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def fetch_prices(
    skus: Sequence[str],
    dest: int,
    *,
    proxies: dict[str, str] | None = None,
    max_retries: int = 3,
    pause: float = 0.7,
    timeout: int = 20,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    import requests

    if not skus:
        return []

    rows: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(_chunks(list(skus), BATCH_SIZE)):
        nm = ";".join(str(s) for s in chunk)
        payload = None
        used_endpoint = None
        last_status: int | None = None
        endpoint_notes: list[str] = []

        global _internal_disabled
        for endpoint in CARD_ENDPOINTS:
            internal = "__internal" in endpoint
            if internal and _internal_disabled:
                continue
            params: dict[str, Any] = {"appType": 1, "curr": "rub", "dest": dest, "spp": 30, "nm": nm}
            if internal:
                params.update(INTERNAL_PARAMS)
                headers = dict(INTERNAL_HEADERS)
                headers["referer"] = f"https://www.wildberries.ru/catalog/{chunk[0]}/detail.aspx"
                headers["deviceid"] = f"site_{uuid.uuid4().hex}"
            else:
                params.update({"hide_dtype": 15, "lang": "ru"})
                headers = dict(HEADERS)

            for attempt in range(1, max_retries + 1):
                try:
                    response = requests.get(
                        endpoint, params=params, headers=headers,
                        proxies=proxies, timeout=timeout,
                    )
                except Exception as exc:
                    endpoint_notes.append(f"{'internal' if internal else 'card.wb.ru'}: {type(exc).__name__}")
                    time.sleep(2 ** attempt)
                    continue

                last_status = response.status_code
                if response.status_code == 429:
                    wait = 2 ** attempt + 1
                    if verbose:
                        print(f"      429 — жду {wait} с")
                    time.sleep(wait)
                    continue
                if response.status_code == WB_TOKEN_REQUIRED and internal:
                    if not _internal_disabled:
                        endpoint_notes.append("internal требует токен сессии")
                        _internal_disabled = True
                    break
                if response.status_code != 200:
                    endpoint_notes.append(f"{'internal' if internal else 'card.wb.ru'}: HTTP {response.status_code}")
                    break
                try:
                    payload = response.json()
                except Exception:
                    endpoint_notes.append(f"{'internal' if internal else 'card.wb.ru'}: не JSON")
                    break
                used_endpoint = endpoint
                break
            if payload is not None:
                break

        if payload is None:
            raise WbError(
                f"WB не отдал данные (последний статус {last_status}). "
                f"Попытки: {'; '.join(endpoint_notes) or 'нет деталей'}"
            )

        parsed = parse_products(payload)
        if verbose:
            short = "internal" if "__internal" in (used_endpoint or "") else "card.wb.ru"
            note = f" | до него: {endpoint_notes[0]}" if endpoint_notes and short == "card.wb.ru" else ""
            print(f"      пачка {chunk_index + 1}: {len(parsed)} из {len(chunk)} SKU ({short}){note}")
        rows.extend(parsed)

        if pause:
            time.sleep(pause)

    return rows


def compare_delivery_by_city(rows: Sequence[dict[str, Any]]) -> list[str]:
    by_sku: dict[str, dict[str, int]] = {}
    for row in rows:
        hours = row.get("delivery_h")
        if isinstance(hours, int):
            by_sku.setdefault(str(row["sku"]), {})[str(row["city"])] = hours

    lines: list[str] = []
    for sku, cities in sorted(by_sku.items()):
        if len(cities) < 2 or len(set(cities.values())) == 1:
            continue
        detail = ", ".join(f"{code}={hours}ч" for code, hours in sorted(cities.items(), key=lambda kv: kv[1]))
        lines.append(f"  {sku}: {detail}")
    return lines


def compare_stock_by_city(rows: Sequence[dict[str, Any]]) -> list[str]:
    by_sku: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row.get("qty") is None:
            continue
        by_sku.setdefault(str(row["sku"]), {})[str(row["city"])] = {
            "qty": int(row["qty"]),
            "wh": row.get("wh_count") or 0,
            "delivery": row.get("delivery_h"),
        }

    lines: list[str] = []
    for sku, cities in sorted(by_sku.items()):
        if len(cities) < 2:
            continue
        if len({c["qty"] for c in cities.values()}) == 1:
            continue
        detail = ", ".join(
            f"{code}={info['qty']} шт/{info['wh']} скл"
            + (f"/{info['delivery']}ч" if info.get("delivery") is not None else "")
            for code, info in sorted(cities.items(), key=lambda kv: -kv[1]["qty"])
        )
        empty = [code for code, info in cities.items() if info["qty"] == 0]
        tail = f"  ← нет в наличии: {', '.join(empty)}" if empty else ""
        lines.append(f"  {sku}: {detail}{tail}")
    return lines


def compare_by_city(rows: Sequence[dict[str, Any]]) -> list[str]:
    by_sku: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.get("price") is None:
            continue
        by_sku.setdefault(str(row["sku"]), {})[str(row["city"])] = float(row["price"])

    lines: list[str] = []
    for sku, prices in sorted(by_sku.items()):
        if len(prices) < 2:
            continue
        values = set(prices.values())
        if len(values) == 1:
            continue
        cheapest = min(prices, key=prices.get)
        dearest = max(prices, key=prices.get)
        delta = prices[dearest] - prices[cheapest]
        share = delta / prices[cheapest] * 100
        detail = ", ".join(f"{c}={p:.0f}" for c, p in sorted(prices.items(), key=lambda kv: kv[1]))
        lines.append(f"  {sku}: {detail}  → разница {delta:.0f} ₽ ({share:.1f}%)")
    return lines


def _main() -> int:
    parser = argparse.ArgumentParser(description="Цены Wildberries по регионам, через БД")
    parser.add_argument("--city", action="append", default=[], help="код города (можно повторять)")
    parser.add_argument("--all-cities", action="store_true", help="все города из БД")
    parser.add_argument("--sku", action="append", default=[], help="ручной артикул WB (можно повторять)")
    parser.add_argument("--client-key", default=None, help="фильтр по конкретному клиенту")
    parser.add_argument("--proxy", default=None, help="host:port:user:pass или URL")
    
    db_group = parser.add_argument_group("работа с базой данных")
    db_group.add_argument("--cities-table", default="wb_parser_cities", help="таблица со списком городов")
    db_group.add_argument("--sku-table", default="wb_parser_target_skus", help="таблица со списком артикулов")
    db_group.add_argument("--results-table", default="wb_frontend_stocks_daily", help="таблица для записи результата")
    args = parser.parse_args()

    conn = None
    try:
        conn = mp_utils.get_db_connection(DB_CONFIG)
    except Exception as exc:
        print(f"❌ база недоступна: {exc}")
        return 2

    try:
        conn = mp_utils.get_db_connection(DB_CONFIG, conn)
        cities = load_cities(conn, args.cities_table)
    except Exception as exc:
        print(f"❌ не удалось загрузить города из БД: {exc}")
        if conn:
            conn.close()
        return 2

    # Если города не указаны явно через --city или --all-cities, берем все города из таблицы по умолчанию
    codes = list(cities) if (args.all_cities or not args.city) else args.city
    if not codes:
        print("В таблице городов нет записей.")
        if conn:
            conn.close()
        return 2

    unknown = [c for c in codes if c not in cities]
    if unknown:
        print(f"❌ Нет таких городов в БД: {', '.join(unknown)}")
        if conn:
            conn.close()
        return 2

    # Загружаем SKU по клиентам из wb_parser_target_skus
    try:
        conn = mp_utils.get_db_connection(DB_CONFIG, conn)
        client_skus = load_target_skus(conn, args.sku_table, args.client_key)
    except Exception as exc:
        print(f"❌ не удалось загрузить SKU из БД: {exc}")
        if conn:
            conn.close()
        return 2

    # Если переданы ручные SKU через аргумент командной строки, добавляем их для client_key (или "default")
    if args.sku:
        manual_key = args.client_key or "default"
        client_skus.setdefault(manual_key, []).extend(args.sku)

    if not client_skus:
        print("Укажи товары: --sku 629760017 или добавьте артикулы в таблицу wb_parser_target_skus")
        if conn:
            conn.close()
        return 2

    proxies = parse_proxy(args.proxy)
    stamp = datetime.now().isoformat(timespec="seconds")
    total_saved = 0

    print("=== Цены Wildberries по регионам (Frontend Parser) ===")
    print(f"    городов: {len(codes)} | клиентов: {len(client_skus)}")
    print(f"    прокси: {'да' if proxies else 'нет, прямое соединение'}\n")

    for client_key, skus in client_skus.items():
        skus = list(dict.fromkeys(skus))
        print(f"🏢 Клиент: {client_key} (товаров: {len(skus)})")

        client_rows: list[dict[str, Any]] = []
        failures: list[str] = []

        for code in codes:
            city = cities[code]
            print(f"  ▶ {city['name']} ({code})")
            try:
                if city.get("dest") is not None:
                    dest = int(city["dest"])
                else:
                    dest = resolve_dest(code, city, proxies=proxies)
            except Exception as exc:
                print(f"     ❌ dest не получен: {exc}")
                failures.append(code)
                continue
            print(f"        dest={dest}")

            try:
                rows = fetch_prices(skus, dest, proxies=proxies, verbose=True)
            except WbError as exc:
                print(f"     ❌ {exc}")
                failures.append(code)
                continue

            for row in rows:
                row.update(city=code, city_name=city["name"], dest=dest, collected_at=stamp)
            client_rows.extend(rows)
            got = sum(1 for r in rows if r.get("price"))
            stock = sum(int(r.get("qty") or 0) for r in rows)
            wh_ids = sorted({s.get("wh") for r in rows for s in (r.get("_stocks") or []) if s.get("wh")})
            shown = ", ".join(str(w) for w in wh_ids[:6]) + ("…" if len(wh_ids) > 6 else "")
            print(f"        цен: {got} | остаток: {stock} шт | склады: {shown or 'разбивки нет'}\n")

        if args.results_table and client_rows:
            try:
                conn = mp_utils.get_db_connection(DB_CONFIG, conn)
                saved = save_results(conn, args.results_table, client_key, client_rows)
                conn.commit()
                total_saved += saved
                print(f"  💾 БД: записано/обновлено {saved} строк для клиента {client_key} в {args.results_table}")
            except Exception as exc:
                print(f"  ❌ Ошибка записи в БД для {client_key}: {exc}")
                if conn:
                    conn.rollback()

        print("-" * 58)

    print(f"\nВсего успешно записано строк в БД: {total_saved}")
    if conn:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(_main())