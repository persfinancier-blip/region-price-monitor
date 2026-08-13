"""Цены Wildberries по регионам. Без браузера, без кук, без человека.

Почему WB проще Ozon: регион задаётся параметром `dest` в самом запросе, а не сессией.
Значит один процесс может опрашивать сколько угодно городов подряд, и ему не нужны
ни прогретые куки, ни прокси, ни капча. Прокси опционален — только если хочется,
чтобы IP совпадал с городом.

Схема:
    город → координаты → geo-API WB → dest → batch-запрос цен → CSV

`dest` кэшируется в dest_cache.json: он меняется редко, дёргать гео каждый раз незачем.

Установка:
    pip install requests

Запуск:
    python wb_price.py --city msk --city nvs --sku 629760017
    python wb_price.py --all-cities --sku-file sku.csv --csv results
    python wb_price.py --list-cities
    python wb_price.py --city msk --sku 629760017 --proxy host:port:user:pass
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

HERE = Path(__file__).resolve().parent
CITIES_FILE = HERE / "cities.json"
DEST_CACHE = HERE / "dest_cache.json"

GEO_URL = "https://user-geo-data.wildberries.ru/get-geo-info"

# WB несколько раз переносил карточный эндпоинт. Пробуем по очереди:
# первый — свежий внутренний (снят из DevTools 11.08.2026), второй — классический.
CARD_ENDPOINTS = (
    "https://www.wildberries.ru/__internal/u-card/cards/v4/detail",
    "https://card.wb.ru/cards/v4/detail",
)

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wildberries.ru/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}

# Внутренний эндпоинт живёт под тем же origin, что и сайт, и хочет свой набор
# заголовков — снято из DevTools 11.08.2026. Без них он не отвечает, и мы
# незаметно откатываемся на card.wb.ru, который остатки по регионам не делит.
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

# Параметры, которые сайт шлёт вместе с dest. hide_vflags/mtype влияют на состав ответа.
INTERNAL_PARAMS = {
    "hide_vflags": "4294967296",
    "hide_dtype": "15",
    "mtype": "257",
    "lang": "ru",
    "ab_testing": "false",
}

BATCH_SIZE = 50          # сколько артикулов в одном запросе
WALLET_DISCOUNT = 0.02   # скидка WB-кошелька, оценочная — точного поля в ответе нет

# HTTP 498 у WB означает «нужен валидный токен сессии» (кука x_wbaas_token).
# Внутренний эндпоинт без него не работает, публичный card.wb.ru — работает.
WB_TOKEN_REQUIRED = 498

_internal_disabled = False   # выставляется на первом 498, чтобы не долбить впустую


class WbError(RuntimeError):
    """Не удалось получить данные WB."""


# ──────────────────────────────────────────────────────────────
# города и dest
# ──────────────────────────────────────────────────────────────

def load_cities() -> dict[str, dict[str, Any]]:
    if not CITIES_FILE.exists():
        raise WbError(f"нет файла городов: {CITIES_FILE}")
    with CITIES_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _load_cache() -> dict[str, Any]:
    if DEST_CACHE.exists():
        try:
            with DEST_CACHE.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    DEST_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_dest(
    code: str,
    city: dict[str, Any],
    *,
    proxies: dict[str, str] | None = None,
    force: bool = False,
    timeout: int = 20,
) -> int:
    """Спросить у WB `dest` для города. Результат кэшируется.

    Гео-эндпоинт отдаёт строку `xinfo` вида `...&dest=-1257786&...` — нужное число там.
    """
    import requests

    cache = _load_cache()
    if not force and code in cache and cache[code].get("dest") is not None:
        return int(cache[code]["dest"])

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
    else:  # на случай, если WB положит dest отдельным полем
        for key in ("dest", "destId", "dest_id"):
            if payload.get(key) is not None:
                try:
                    dest = int(payload[key])
                    break
                except (TypeError, ValueError):
                    continue

    if dest is None:
        raise WbError(f"в ответе гео-API нет dest для города {code}: ключи {sorted(payload)[:10]}")

    cache[code] = {
        "dest": dest,
        "name": city["name"],
        "resolved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(cache)
    return dest


# ──────────────────────────────────────────────────────────────
# прокси
# ──────────────────────────────────────────────────────────────

PROXY_FILE = HERE / "proxy.json"

# Сервисы проверки выходного IP. Первый — тот же, что в панелях прокси-провайдеров.
IP_ECHO_URLS = ("https://api.i.pn/json/", "https://ipwho.is/", "https://ipinfo.io/json")


def load_proxy_file(path: str | Path | None = None) -> dict[str, Any] | None:
    """Прочитать proxy.json: {host, port, user, password} либо {url}."""
    source = Path(path) if path else PROXY_FILE
    if not source.exists():
        return None
    with source.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) and (data.get("host") or data.get("url")) else None


def build_proxy(
    raw: str | None = None,
    *,
    host: str | None = None,
    port: str | int | None = None,
    user: str | None = None,
    password: str | None = None,
    from_file: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Собрать прокси из чего угодно: строки, отдельных полей или proxy.json.

    Принимаются формы:
        host:port:user:pass         — как в панелях провайдеров
        host:port
        http://user:pass@host:port  — готовая ссылка
        отдельные --proxy-host / --proxy-user / --proxy-pass
        proxy.json
    """
    if from_file and not any((raw, host)):
        if from_file.get("url"):
            raw = str(from_file["url"])
        else:
            host = str(from_file.get("host") or "")
            port = from_file.get("port") or 443
            user = from_file.get("user") or from_file.get("login") or ""
            password = from_file.get("password") or from_file.get("pass") or ""

    if host:
        credentials = f"{user}:{password}@" if user else ""
        url = f"http://{credentials}{host}:{port or 443}"
    elif raw:
        raw = raw.strip()
        if "://" in raw:
            url = raw
        else:
            parts = raw.split(":")
            if len(parts) == 4:
                p_host, p_port, p_user, p_pass = parts
                url = f"http://{p_user}:{p_pass}@{p_host}:{p_port}"
            elif len(parts) == 2:
                url = f"http://{parts[0]}:{parts[1]}"
            else:
                raise SystemExit(f"Не понимаю формат прокси: {raw!r}")
    else:
        return None

    return {"http": url, "https": url}


# оставлено для совместимости со старыми вызовами
def parse_proxy(raw: str | None) -> dict[str, str] | None:
    return build_proxy(raw)


def mask_proxy(proxies: dict[str, str] | None) -> str:
    """Показать прокси без пароля."""
    if not proxies:
        return "нет, прямое соединение"
    return re.sub(r"//[^@/]+@", "//***@", proxies.get("https", ""))


class Traffic:
    """Счётчик трафика. Мобильные прокси тарифицируются по гигабайтам,
    поэтому знать расход за прогон важнее, чем кажется."""

    def __init__(self) -> None:
        self.sent = 0
        self.received = 0
        self.requests = 0

    def account(self, response: Any) -> None:
        self.requests += 1
        try:
            request = response.request
            head = f"{request.method} {request.url}\r\n"
            head += "".join(f"{k}: {v}\r\n" for k, v in (request.headers or {}).items())
            self.sent += len(head.encode("utf-8", "replace"))
            if getattr(request, "body", None):
                body = request.body
                self.sent += len(body if isinstance(body, bytes) else str(body).encode("utf-8", "replace"))
        except Exception:
            pass
        try:
            # Content-Length — это байты «по проводу», то есть уже сжатые.
            # Именно их считает провайдер. Без заголовка берём распакованный размер.
            length = response.headers.get("Content-Length") if response.headers else None
            self.received += int(length) if length else len(response.content or b"")
            self.received += sum(
                len(f"{k}: {v}\r\n".encode("utf-8", "replace")) for k, v in (response.headers or {}).items()
            )
        except Exception:
            pass

    @property
    def total(self) -> int:
        return self.sent + self.received

    @staticmethod
    def human(size: int) -> str:
        if size < 1024:
            return f"{size} Б"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        return f"{size / 1024 / 1024:.2f} МБ"

    def report(self, cities: int = 1, skus: int = 1) -> list[str]:
        lines = [
            f"  Трафик: {self.human(self.total)} за {self.requests} запросов "
            f"(принято {self.human(self.received)}, отправлено {self.human(self.sent)})"
        ]
        if cities > 0 and skus > 0 and self.total:
            per_sku_city = self.total / (cities * skus)
            month = per_sku_city * skus * cities * 24 * 30
            lines.append(
                f"  На один товар в одном городе: {self.human(int(per_sku_city))} | "
                f"тем же составом ежечасно — {self.human(int(month))} в месяц"
            )
        return lines


def _swap_scheme(proxies: dict[str, str], scheme: str) -> dict[str, str]:
    """Пересобрать адрес прокси под другую схему, сохранив логин и пароль."""
    url = re.sub(r"^\w+://", f"{scheme}://", proxies["https"])
    return {"http": url, "https": url}


def check_proxy(
    proxies: dict[str, str] | None,
    traffic: Traffic | None = None,
    timeout: int = 20,
) -> dict[str, Any] | None:
    """Показать выходной IP, город и оператора — то же, что делает `curl i.pn`.

    Попутно подбирается схема соединения с самим прокси. Часть провайдеров слушает
    plain HTTP, часть ждёт TLS (обычно это порт 443), и угадать по порту нельзя.
    Если рабочей окажется другая схема, словарь `proxies` правится на месте —
    дальше все запросы пойдут уже по ней.
    """
    import requests

    if proxies is None:
        schemes: list[dict[str, str] | None] = [None]
    else:
        current = proxies["https"].split("://", 1)[0]
        other = "https" if current == "http" else "http"
        schemes = [proxies, _swap_scheme(proxies, other)]

    for candidate in schemes:
        for url in IP_ECHO_URLS:
            try:
                response = requests.get(url, proxies=candidate, timeout=timeout,
                                        headers={"User-Agent": HEADERS["User-Agent"]})
            except Exception:
                continue
            if traffic:
                traffic.account(response)
            if response.status_code != 200:
                continue
            try:
                data = response.json()
            except Exception:
                continue
            info = {
                "ip": data.get("query") or data.get("ip"),
                "city": data.get("city"),
                "region": data.get("regionName") or data.get("region"),
                "operator": data.get("isp") or data.get("org") or (data.get("connection") or {}).get("isp"),
                "mobile": data.get("mobile"),
                "source": url,
            }
            if info["ip"]:
                if proxies is not None and candidate is not proxies:
                    proxies.update(candidate)   # рабочая схема — на весь дальнейший прогон
                    info["scheme_switched_to"] = candidate["https"].split("://", 1)[0]
                return info
    return None


# ──────────────────────────────────────────────────────────────
# разбор цен
# ──────────────────────────────────────────────────────────────

def _kopecks(value: Any) -> float | None:
    """WB отдаёт цены в копейках целым числом."""
    if value is None:
        return None
    try:
        number = float(value) / 100
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def collect_stocks(product: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Разложить остатки по складам, которые WB показал для этого `dest`.

    Важно: список складов зависит от региона. На один и тот же товар Москва и
    Владивосток получают разные склады с разными остатками — в этом весь смысл
    регионального мониторинга.

    Возвращает (суммарный остаток, строки по складам).
    `time1`/`time2` — сроки доставки в часах: быстрый и обычный вариант.
    """
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
    """Достать цены и остатки из ответа карточного эндпоинта.

    Структура: data.products[].sizes[].price  = {basic, product, total, logistics}
               data.products[].sizes[].stocks = [{wh, qty, time1, time2}, ...]
    basic   — до скидки (зачёркнутая)
    product — цена продажи
    total   — итог с учётом логистики, если WB его отдаёт
    """
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
            # На части карточек WB отдаёт только сводное число без разбивки.
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
            # Точного поля скидки кошелька в ответе нет — это оценка, не факт.
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


# ──────────────────────────────────────────────────────────────
# запрос цен
# ──────────────────────────────────────────────────────────────

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
    raw_dir: str | Path | None = None,
    traffic: Traffic | None = None,
) -> list[dict[str, Any]]:
    """Batch-запрос цен и остатков для списка артикулов в одном регионе."""
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
                # same-origin: реферер должен указывать на карточку товара
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

                if traffic:
                    traffic.account(response)
                last_status = response.status_code
                if response.status_code == 429:
                    wait = 2 ** attempt + 1
                    if verbose:
                        print(f"      429 — жду {wait} с")
                    time.sleep(wait)
                    continue
                if response.status_code == WB_TOKEN_REQUIRED and internal:
                    if not _internal_disabled:
                        endpoint_notes.append("internal требует токен сессии — дальше только card.wb.ru")
                        _internal_disabled = True
                    break
                if response.status_code != 200:
                    endpoint_notes.append(f"{'internal' if internal else 'card.wb.ru'}: HTTP {response.status_code}")
                    break  # другой эндпоинт может ответить лучше
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

        if raw_dir:
            dump = Path(raw_dir)
            dump.mkdir(parents=True, exist_ok=True)
            (dump / f"wb_raw_dest{dest}_chunk{chunk_index + 1}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
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


# ──────────────────────────────────────────────────────────────
# ввод-вывод
# ──────────────────────────────────────────────────────────────

def load_skus(path: str | Path) -> list[str]:
    """Прочитать артикулы из CSV. Понимает колонки marketplace/sku и просто sku."""
    source = Path(path)
    if not source.exists():
        raise SystemExit(f"Файл со списком SKU не найден: {source}")

    skus: list[str] = []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        if "," in sample or ";" in sample or "\t" in sample:
            reader = csv.DictReader(handle, delimiter=";" if sample.count(";") > sample.count(",") else ",")
            for row in reader:
                low = {str(k).strip().lower(): v for k, v in row.items() if k}
                marketplace = str(low.get("marketplace", "wb")).strip().lower()
                if marketplace and marketplace != "wb":
                    continue
                value = str(low.get("sku") or low.get("nm") or low.get("артикул") or "").strip()
                if value.isdigit():
                    skus.append(value)
        else:
            for line in handle:
                line = line.strip()
                if line.isdigit():
                    skus.append(line)

    if not skus:
        raise SystemExit(f"В {source} не нашлось ни одного артикула WB")
    return skus


def save_csv(rows: Sequence[dict[str, Any]], out_dir: str | Path) -> Path:
    """Сводная таблица: строка на товар в городе."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    path = directory / f"wb_prices_{stamp}.csv"
    fields = [
        "city", "city_name", "dest", "sku", "name", "brand",
        "price", "price_base", "price_total", "price_wallet_est", "currency",
        "qty", "wh_count", "wh_main", "wh_main_qty", "delivery_h",
        "is_available", "supplier", "rating", "collected_at",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def save_stocks_csv(rows: Sequence[dict[str, Any]], out_dir: str | Path) -> Path | None:
    """Детальная таблица: строка на связку товар × город × склад."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    path = directory / f"wb_stocks_{stamp}.csv"

    detailed: list[dict[str, Any]] = []
    for row in rows:
        for stock in row.get("_stocks") or []:
            detailed.append({
                "city": row.get("city"),
                "city_name": row.get("city_name"),
                "dest": row.get("dest"),
                "sku": row.get("sku"),
                "name": row.get("name"),
                "wh": stock.get("wh"),
                "size": stock.get("size"),
                "qty": stock.get("qty"),
                "delivery_h1": stock.get("delivery_h1"),
                "delivery_h2": stock.get("delivery_h2"),
                "price": row.get("price"),
                "collected_at": row.get("collected_at"),
            })
    if not detailed:
        return None

    fields = [
        "city", "city_name", "dest", "sku", "name",
        "wh", "size", "qty", "delivery_h1", "delivery_h2", "price", "collected_at",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(detailed)
    return path


def compare_delivery_by_city(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Сроки доставки по городам.

    Это второй региональный сигнал, независимый от цены. Даже когда товар лежит
    на одном складе и остаток везде одинаковый, сроки до разных городов разные —
    и это доказывает, что `dest` учитывается по-настоящему.
    """
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
    """Где остаток различается между городами — это и есть картина по складам."""
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
    """Короткая сводка: у каких SKU цена различается между городами."""
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


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def _main() -> int:
    parser = argparse.ArgumentParser(description="Цены Wildberries по регионам, без браузера")
    parser.add_argument("--city", action="append", default=[], help="код города (можно повторять)")
    parser.add_argument("--all-cities", action="store_true", help="все города из cities.json")
    parser.add_argument("--sku", action="append", default=[], help="артикул WB (можно повторять)")
    parser.add_argument("--sku-file", default=None, help="CSV со списком артикулов")
    parser.add_argument("--csv", default=None, help="папка для CSV с результатом")
    proxy_group = parser.add_argument_group("прокси")
    proxy_group.add_argument("--proxy", default=None, help="host:port:user:pass или готовая ссылка")
    proxy_group.add_argument("--proxy-host", default=None, help="хост прокси")
    proxy_group.add_argument("--proxy-port", default=443, help="порт (по умолчанию 443)")
    proxy_group.add_argument("--proxy-user", default=None, help="логин")
    proxy_group.add_argument("--proxy-pass", default=None, help="пароль")
    proxy_group.add_argument("--proxy-file", default=None, help=f"файл с прокси (по умолчанию {PROXY_FILE.name})")
    proxy_group.add_argument("--no-proxy", action="store_true", help="игнорировать proxy.json, идти напрямую")
    proxy_group.add_argument("--check-proxy", action="store_true", help="показать выходной IP и выйти")
    parser.add_argument("--refresh-dest", action="store_true", help="перезапросить dest, игнорируя кэш")
    parser.add_argument("--list-cities", action="store_true", help="показать города и выйти")
    parser.add_argument("--json", action="store_true", help="вывести результат как JSON")
    parser.add_argument("--raw-dir", default=None, help="куда складывать сырые ответы WB для разбора")

    db_group = parser.add_argument_group("работа с базой (сервер)")
    db_group.add_argument("--db-url", default=None,
                          help="postgresql://user:pass@host:5432/db или sqlite:///file.db; "
                               "иначе берётся RPM_DB_URL или PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
    db_group.add_argument("--cities-table", default=None, help="таблица со списком городов")
    db_group.add_argument("--sku-table", default=None, help="таблица со списком артикулов")
    db_group.add_argument("--results-table", default=None, help="таблица для записи результата")
    args = parser.parse_args()

    # Проверка прокси не требует ни городов, ни товаров — обрабатываем первой.
    if args.check_proxy:
        probe_traffic = Traffic()
        probe_proxies = None
        if not args.no_proxy:
            probe_proxies = build_proxy(
                args.proxy, host=args.proxy_host, port=args.proxy_port,
                user=args.proxy_user, password=args.proxy_pass,
                from_file=load_proxy_file(args.proxy_file),
            )
        print("=== Проверка прокси ===")
        print(f"    прокси: {mask_proxy(probe_proxies)}")
        info = check_proxy(probe_proxies, probe_traffic)
        if info:
            mobile = " · мобильный" if info.get("mobile") else ""
            print(f"    выходной IP: {info['ip']} · {info.get('city') or '?'} · "
                  f"{info.get('region') or '?'} · {info.get('operator') or '?'}{mobile}")
            print(f"    ответил: {info['source']}")
        else:
            print("    ❌ выходной IP определить не удалось — прокси не отвечает")
        for line in probe_traffic.report():
            print(line)
        return 0 if info else 1

    use_db = any((args.cities_table, args.sku_table, args.results_table))
    db = None
    wb_db = None
    if use_db:
        try:
            import wb_db as wb_db_module
            wb_db = wb_db_module
            db = wb_db.connect(args.db_url)
        except Exception as exc:
            print(f"❌ база недоступна: {exc}")
            return 2

    try:
        cities = wb_db.load_cities(db, args.cities_table) if args.cities_table else load_cities()
    except Exception as exc:
        print(f"❌ {exc}")
        if db:
            db.close()
        return 2

    if args.list_cities:
        cache = _load_cache()
        print(f"Города в {CITIES_FILE.name}:\n")
        for code, city in sorted(cities.items()):
            dest = cache.get(code, {}).get("dest")
            print(f"  {code:8} {city['name']:22} dest={dest if dest is not None else '— (ещё не запрашивали)'}")
        return 0

    codes = list(cities) if args.all_cities else args.city
    if not codes:
        print("Укажи хотя бы один город: --city msk  (или --all-cities, или --list-cities)")
        return 2
    unknown = [c for c in codes if c not in cities]
    if unknown:
        print(f"❌ Нет таких городов в cities.json: {', '.join(unknown)}")
        return 2

    skus = list(args.sku)
    if args.sku_file:
        skus.extend(load_skus(args.sku_file))
    if args.sku_table:
        try:
            skus.extend(wb_db.load_skus(db, args.sku_table))
        except Exception as exc:
            print(f"❌ {exc}")
            db.close()
            return 2
    if not skus:
        print("Укажи товары: --sku 629760017, --sku-file sku.csv или --sku-table parser_skus")
        return 2
    skus = list(dict.fromkeys(skus))  # без дублей, порядок сохраняется

    traffic = Traffic()
    proxies = None
    if not args.no_proxy:
        proxies = build_proxy(
            args.proxy,
            host=args.proxy_host,
            port=args.proxy_port,
            user=args.proxy_user,
            password=args.proxy_pass,
            from_file=load_proxy_file(args.proxy_file),
        )
    verbose = not args.json

    if verbose:
        print("=== Цены Wildberries по регионам ===")
        print(f"    товаров: {len(skus)} | городов: {len(codes)}")
        print(f"    прокси: {mask_proxy(proxies)}")

    if proxies:
        info = check_proxy(proxies, traffic)
        if info:
            mobile = " · мобильный" if info.get("mobile") else ""
            print(f"    выходной IP: {info['ip']} · {info.get('city') or '?'} · "
                  f"{info.get('operator') or '?'}{mobile}")
            if info.get("scheme_switched_to"):
                print(f"    схема прокси: {info['scheme_switched_to']} (подобрана автоматически)")
        else:
            print("    ⚠️  выходной IP определить не удалось — прокси может не работать")
            print("       (сбор всё равно попробую; сравнить можно через --no-proxy)")
    print()

    stamp = datetime.now().isoformat(timespec="seconds")
    all_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for code in codes:
        city = cities[code]
        if verbose:
            print(f"▶ {city['name']} ({code})")
        try:
            if city.get("dest") is not None and not args.refresh_dest:
                dest = int(city["dest"])   # dest пришёл прямо из таблицы — гео не дёргаем
            else:
                dest = resolve_dest(code, city, proxies=proxies, force=args.refresh_dest)
        except Exception as exc:
            print(f"   ❌ dest не получен: {exc}")
            failures.append(code)
            continue
        if verbose:
            print(f"      dest={dest}")

        try:
            rows = fetch_prices(skus, dest, proxies=proxies, verbose=verbose,
                                raw_dir=args.raw_dir, traffic=traffic)
        except WbError as exc:
            print(f"   ❌ {exc}")
            failures.append(code)
            continue

        for row in rows:
            row.update(city=code, city_name=city["name"], dest=dest, collected_at=stamp)
        all_rows.extend(rows)
        if verbose:
            got = sum(1 for r in rows if r.get("price"))
            stock = sum(int(r.get("qty") or 0) for r in rows)
            wh_ids = sorted({s.get("wh") for r in rows for s in (r.get("_stocks") or []) if s.get("wh")})
            shown = ", ".join(str(w) for w in wh_ids[:6]) + ("…" if len(wh_ids) > 6 else "")
            print(f"      цен: {got} | остаток: {stock} шт | склады: {shown or 'разбивки нет'}\n")

    if args.json:
        print(json.dumps(all_rows, ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print("  СОБРАННЫЕ ДАННЫЕ")
        print()
        print(f"  {'Артикул':<12} {'Город':<6} {'Цена':>8} {'Без скидки':>11} "
              f"{'Кошелёк≈':>9} {'Остаток':>8} {'Склад':>8} {'Доставка':>9}")
        print("  " + "-" * 74)
        for row in sorted(all_rows, key=lambda r: (str(r.get("sku")), str(r.get("city")))):
            price = f"{row['price']:.0f}" if row.get("price") else "—"
            base = f"{row['price_base']:.0f}" if row.get("price_base") else "—"
            wallet = f"{row['price_wallet_est']:.0f}" if row.get("price_wallet_est") else "—"
            qty = str(row.get("qty") if row.get("qty") is not None else "—")
            wh = str(row.get("wh_main") or "—")
            delivery = f"{row['delivery_h']}ч" if row.get("delivery_h") is not None else "—"
            print(f"  {str(row.get('sku')):<12} {str(row.get('city')):<6} {price:>8} {base:>11} "
                  f"{wallet:>9} {qty:>8} {wh:>8} {delivery:>9}")
        print()
        print(f"  Всего строк: {len(all_rows)}")
        if failures:
            print(f"  Города без данных: {', '.join(failures)}")

        diff = compare_by_city(all_rows)
        if diff:
            print("\n  Цена различается по городам:")
            for line in diff[:20]:
                print(line)
            if len(diff) > 20:
                print(f"  ... и ещё {len(diff) - 20} товаров")
        elif len(codes) > 1:
            print("\n  Ни у одного товара цена по городам не различается.")

        stock_diff = compare_stock_by_city(all_rows)
        if stock_diff:
            print("\n  Остаток различается по городам:")
            for line in stock_diff[:20]:
                print(line)
            if len(stock_diff) > 20:
                print(f"  ... и ещё {len(stock_diff) - 20} товаров")
        elif len(codes) > 1 and all_rows:
            same_wh = len({s.get("wh") for r in all_rows for s in (r.get("_stocks") or [])}) <= 1
            print("\n  Остаток по городам одинаковый.")
            if same_wh:
                print("  Во всех городах один и тот же склад — товар лежит на одном")
                print("  центральном складе и оттуда развозится по стране. Это нормально.")

        delivery = compare_delivery_by_city(all_rows)
        if delivery:
            print("\n  Срок доставки различается по городам:")
            for line in delivery[:20]:
                print(line)

        print()
        for line in traffic.report(cities=len(codes), skus=len(skus)):
            print(line)
        print("=" * 78)

    if args.csv and all_rows:
        path = save_csv(all_rows, args.csv)
        print(f"CSV (сводка):  {path}")
        stocks_path = save_stocks_csv(all_rows, args.csv)
        if stocks_path:
            print(f"CSV (склады):  {stocks_path}")
        else:
            print("CSV (склады):  WB не отдал разбивку по складам для этих товаров")

    if args.results_table and all_rows:
        try:
            saved = wb_db.save_results(db, args.results_table, all_rows)
            print(f"БД: записано {saved} строк в {args.results_table}")
        except Exception as exc:
            print(f"❌ в БД записать не удалось: {exc}")
            db.close()
            return 1

    if db:
        db.close()
    return 0 if all_rows else 1


if __name__ == "__main__":
    sys.exit(_main())
