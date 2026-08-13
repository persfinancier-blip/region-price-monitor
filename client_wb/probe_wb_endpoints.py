# -*- coding: utf-8 -*-
"""
Проба эндпоинтов Wildberries: какой из них жив и какой отдаёт ОСТАТКИ ПО СКЛАДАМ,
а не только цену.

Ничего не пишет в БД, ничего не меняет. Только читает и печатает отчёт.

Запуск (Windows):
    python probe_wb_endpoints.py --proxy host:port:user:pass
    python probe_wb_endpoints.py                      # прокси возьмётся из proxy.txt или WB_PROXY
    python probe_wb_endpoints.py --allow-direct       # без прокси, только для отладки
    python probe_wb_endpoints.py --cookie "x_wbaas_token=..."   # проверить внутренний эндпоинт

Что делает:
  1. проверяет выходной IP (чтобы было видно, через что реально идём);
  2. дёргает один и тот же SKU через набор эндпоинтов на нескольких dest;
  3. по каждому ответу печатает: HTTP, цену, суммарный остаток, список складов;
  4. сравнивает результаты между городами и говорит, есть ли РЕГИОНАЛЬНАЯ разница
     в цене и в складах — то есть годится ли эндпоинт для задачи;
  5. складывает сырые JSON в probe_raw/ и отчёт в probe_report.txt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    print("Нет requests. Установи: pip install requests")
    sys.exit(1)

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "probe_raw"
REPORT = HERE / "probe_report.txt"

# ── что проверяем ────────────────────────────────────────────────────────────

# Товар и города из HANDOFF (проверялись живьём 12.08.2026).
DEFAULT_SKU = "629760017"
DEFAULT_DESTS = {
    "msk": 1259570991,
    "nsk": -364764,
    "vvo": 123587791,
}

PUBLIC_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wildberries.ru/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}

INTERNAL_HEADERS = {
    "accept": "*/*",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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

# Матрица. Порядок значения не имеет — гоняем все и сравниваем.
ENDPOINTS = [
    {"key": "card-v4", "url": "https://card.wb.ru/cards/v4/detail", "profile": "public"},
    {"key": "card-v3", "url": "https://card.wb.ru/cards/v3/detail", "profile": "public"},
    {"key": "card-v2", "url": "https://card.wb.ru/cards/v2/detail", "profile": "public"},
    {"key": "card-v1", "url": "https://card.wb.ru/cards/detail", "profile": "public"},
    {"key": "ucard-v4", "url": "https://u-card.wb.ru/cards/v4/detail", "profile": "public"},
    {"key": "internal-v4",
     "url": "https://www.wildberries.ru/__internal/u-card/cards/v4/detail",
     "profile": "internal"},
]

# Справочник складов — dest-независимый, нужен чтобы номер wh стал читаемым именем.
STORES_URL = "https://static-basket-01.wbbasket.ru/vol0/data/stores-data.json"

IP_SERVICES = [
    "https://api.i.pn/json",
    "https://ipwho.is/",
    "https://ipinfo.io/json",
]

# ── вывод ────────────────────────────────────────────────────────────────────

_lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    _lines.append(text)


def flush_report() -> None:
    REPORT.write_text("\n".join(_lines) + "\n", encoding="utf-8")


# ── прокси ───────────────────────────────────────────────────────────────────

def build_proxy(raw: str | None) -> dict[str, str] | None:
    """host:port:user:pass, host:port или готовый URL."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
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


def mask(proxies: dict[str, str] | None) -> str:
    if not proxies:
        return "нет (прямое соединение)"
    url = proxies.get("https") or proxies.get("http") or ""
    if "@" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def find_proxy(args) -> str | None:
    if args.proxy:
        return args.proxy
    env = os.getenv("WB_PROXY")
    if env:
        return env
    f = HERE / "proxy.txt"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return None


def check_exit_ip(proxies) -> None:
    say("Выходной IP:")
    for url in IP_SERVICES:
        try:
            r = requests.get(url, proxies=proxies, timeout=15)
            if r.status_code != 200:
                say(f"  {url} -> HTTP {r.status_code}")
                continue
            d = r.json()
            ip = d.get("ip") or d.get("query") or "?"
            city = d.get("city") or "?"
            org = d.get("org") or d.get("connection", {}).get("org") or d.get("isp") or "?"
            country = d.get("country") or d.get("country_name") or "?"
            say(f"  {ip}  {country} / {city}  {org}")
            return
        except Exception as exc:
            say(f"  {url} -> {type(exc).__name__}")
    say("  ни один сервис не ответил — проверь прокси, дальше идти смысла мало")


# ── разбор ответа ────────────────────────────────────────────────────────────

def analyze(payload):
    """Достаём из ответа то, ради чего всё: цену и остатки по складам."""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("data")
    products = raw.get("products") if isinstance(raw, dict) else payload.get("products")
    if not products:
        return None
    p = products[0]
    sizes = p.get("sizes") or []

    price = basic = total = None
    stocks = []
    for s in sizes:
        po = s.get("price") or {}
        if price is None and (po.get("product") or po.get("total")):
            price = po.get("product")
            basic = po.get("basic")
            total = po.get("total")
        for st in (s.get("stocks") or []):
            stocks.append({
                "wh": st.get("wh"),
                "qty": st.get("qty"),
                "t1": st.get("time1"),
                "t2": st.get("time2"),
                "dtype": st.get("dtype"),
            })

    def rub(v):
        try:
            return round(float(v) / 100, 2)
        except (TypeError, ValueError):
            return None

    return {
        "sku": p.get("id") or p.get("nmId"),
        "name": p.get("name"),
        "price": rub(price),
        "basic": rub(basic),
        "total": rub(total),
        "sizes": len(sizes),
        "stocks": stocks,
        "qty_sum": sum(int(s["qty"] or 0) for s in stocks),
        "wh_set": sorted({s["wh"] for s in stocks if s["wh"] is not None}),
        "totalQuantity": p.get("totalQuantity"),
        "product_keys": sorted(k for k in p.keys()),
    }


def fetch(ep, sku, dest, proxies, cookie, timeout=25):
    params = {"appType": 1, "curr": "rub", "dest": dest, "spp": 30, "nm": sku}
    if ep["profile"] == "internal":
        params.update(INTERNAL_PARAMS)
        headers = dict(INTERNAL_HEADERS)
        headers["referer"] = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        headers["deviceid"] = f"site_{uuid.uuid4().hex}"
        if cookie:
            headers["cookie"] = cookie
    else:
        params.update({"hide_dtype": 15, "lang": "ru"})
        headers = dict(PUBLIC_HEADERS)

    started = time.time()
    try:
        r = requests.get(ep["url"], params=params, headers=headers,
                         proxies=proxies, timeout=timeout)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "ms": int((time.time() - started) * 1000)}

    out = {
        "status": r.status_code,
        "bytes": len(r.content),
        "ms": int((time.time() - started) * 1000),
        "ctype": r.headers.get("Content-Type", ""),
    }
    if r.status_code != 200:
        out["body_head"] = r.text[:200]
        return out
    try:
        out["payload"] = r.json()
    except Exception:
        out["error"] = "ответ не JSON"
        out["body_head"] = r.text[:200]
    return out


def load_stores(proxies):
    try:
        r = requests.get(STORES_URL, proxies=proxies, timeout=20)
        if r.status_code != 200:
            return {}, f"HTTP {r.status_code}"
        data = r.json()
        out = {}
        for item in data if isinstance(data, list) else []:
            wid = item.get("id")
            if wid is not None:
                out[int(wid)] = item.get("name") or str(wid)
        return out, f"складов в справочнике: {len(out)}"
    except Exception as exc:
        return {}, f"{type(exc).__name__}"


# ── основной прогон ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Проба эндпоинтов WB")
    ap.add_argument("--sku", default=DEFAULT_SKU, help=f"артикул (по умолчанию {DEFAULT_SKU})")
    ap.add_argument("--proxy", default=None, help="host:port:user:pass или URL")
    ap.add_argument("--allow-direct", action="store_true", help="разрешить работу без прокси")
    ap.add_argument("--cookie", default=None, help="строка Cookie для внутреннего эндпоинта")
    ap.add_argument("--pause", type=float, default=1.0, help="пауза между запросами, с")
    args = ap.parse_args()

    RAW_DIR.mkdir(exist_ok=True)

    raw_proxy = find_proxy(args)
    proxies = build_proxy(raw_proxy)
    if proxies is None and not args.allow_direct:
        print("Прокси не задан. Укажи --proxy, положи строку в proxy.txt, задай WB_PROXY")
        print("или запусти с --allow-direct, если сознательно идёшь напрямую.")
        return 2

    say("=" * 78)
    say("ПРОБА ЭНДПОИНТОВ WILDBERRIES")
    say(f"артикул: {args.sku}   городов: {len(DEFAULT_DESTS)}   эндпоинтов: {len(ENDPOINTS)}")
    say(f"прокси:  {mask(proxies)}")
    say("=" * 78)
    say()

    check_exit_ip(proxies)
    say()

    stores, stores_note = load_stores(proxies)
    say(f"Справочник складов: {stores_note}")
    say()

    results = {}   # (ep_key, city) -> analyzed | None

    for ep in ENDPOINTS:
        say("-" * 78)
        say(f"{ep['key']}   {ep['url']}")
        for city, dest in DEFAULT_DESTS.items():
            res = fetch(ep, args.sku, dest, proxies, args.cookie)
            time.sleep(args.pause)

            if "error" in res and "status" not in res:
                say(f"  {city:4} dest={dest:<12} СБОЙ: {res['error']}")
                results[(ep["key"], city)] = None
                continue

            status = res.get("status")
            if status != 200:
                hint = ""
                if status == 498:
                    hint = "  <- нужен токен сессии (кука x_wbaas_token)"
                elif status == 404:
                    hint = "  <- эндпоинта нет"
                say(f"  {city:4} dest={dest:<12} HTTP {status} ({res['ms']} мс){hint}")
                results[(ep["key"], city)] = None
                continue

            payload = res.get("payload")
            if payload is None:
                say(f"  {city:4} dest={dest:<12} HTTP 200, но {res.get('error')}")
                results[(ep["key"], city)] = None
                continue

            (RAW_DIR / f"{ep['key']}__{city}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            a = analyze(payload)
            if a is None:
                say(f"  {city:4} dest={dest:<12} HTTP 200, {res['bytes']} б, но products пуст")
                results[(ep["key"], city)] = None
                continue

            results[(ep["key"], city)] = a
            wh_txt = ", ".join(
                f"{s['wh']}"
                + (f"[{stores[s['wh']]}]" if s["wh"] in stores else "")
                + f":{s['qty']}"
                + (f"/{s['t1']}ч" if s["t1"] is not None else "")
                for s in a["stocks"][:8]
            ) or "разбивки нет"
            if len(a["stocks"]) > 8:
                wh_txt += " ..."
            say(f"  {city:4} dest={dest:<12} HTTP 200  цена={a['price']}  базовая={a['basic']}"
                f"  остаток={a['qty_sum']}  складов={len(a['wh_set'])}")
            say(f"       склады: {wh_txt}")

    # ── выводы ───────────────────────────────────────────────────────────────
    say()
    say("=" * 78)
    say("ВЫВОДЫ")
    say("=" * 78)

    verdicts = []
    for ep in ENDPOINTS:
        got = {c: results.get((ep["key"], c)) for c in DEFAULT_DESTS}
        alive = {c: a for c, a in got.items() if a}
        if not alive:
            say(f"{ep['key']:12} — мёртв или недоступен")
            verdicts.append((ep["key"], False, False, False))
            continue

        prices = {c: a["price"] for c, a in alive.items() if a["price"] is not None}
        regional_price = len(set(prices.values())) > 1 if len(prices) > 1 else False

        has_stocks = any(a["stocks"] for a in alive.values())
        wh_sets = {c: tuple(a["wh_set"]) for c, a in alive.items()}
        regional_wh = len(set(wh_sets.values())) > 1 if len(wh_sets) > 1 else False
        qtys = {c: a["qty_sum"] for c, a in alive.items()}
        regional_qty = len(set(qtys.values())) > 1 if len(qtys) > 1 else False

        say(f"{ep['key']:12} — живых городов {len(alive)}/{len(DEFAULT_DESTS)}")
        say(f"{'':14} цены: {prices}  -> различаются по городам: {'ДА' if regional_price else 'нет'}")
        say(f"{'':14} остатки в ответе: {'ЕСТЬ' if has_stocks else 'НЕТ'}"
            f"   суммы: {qtys}  -> различаются: {'ДА' if regional_qty else 'нет'}")
        say(f"{'':14} наборы складов: {wh_sets}  -> различаются: {'ДА' if regional_wh else 'нет'}")
        verdicts.append((ep["key"], True, has_stocks, regional_price or regional_wh or regional_qty))

    say()
    usable = [k for k, alive, st, reg in verdicts if alive and st]
    say("Годятся для задачи (живы + отдают stocks[]): " + (", ".join(usable) or "НИ ОДИН"))
    regional = [k for k, alive, st, reg in verdicts if alive and reg]
    say("Показывают региональную разницу: " + (", ".join(regional) or "ни один"))
    say()
    say(f"Сырые ответы: {RAW_DIR}")
    say(f"Отчёт:        {REPORT}")

    flush_report()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        flush_report()
        sys.exit(1)
