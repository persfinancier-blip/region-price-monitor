"""Цена Ozon одним HTTP-запросом: curl_cffi + куки из файла + опциональный прокси.

Браузер не открывается. Взаимодействия с человеком нет. Запустил — получил цену.

Механизм (эталон — C:\\Dev\\test_pars_2\\ozon_parser.py, подтверждён живыми выгрузками
results/ozon_msk_*.csv от 2026-07-25/26):

    GET https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/product/<sku>/
        + куки из cookies/ozon/<region>.json
        + заголовки x-o3-* (dweb_client)
        + curl_cffi impersonate="chrome"   ← без него Ozon отдаёт 403 (фингерпринт TLS/JA3)

Ответ — JSON с `widgetStates`, цена лежит в виджете `webPrice`:
    price          — по которой продаётся сейчас
    cardPrice      — с Ozon-картой
    originalPrice  — зачёркнутая

Куки берутся из файла и НИКАК не добываются этим модулем — это отдельный разовый шаг
(см. cookies_from_curl.py: скопировать из DevTools, браузер открывать не надо).
Регион зашит в куке, а не в IP: один файл кук = один город.

CLI:
    python ozon_price.py 1964684436 --cookies cookies/ozon/msk.json
    python ozon_price.py 1964684436 2223334445 --cookies cookies/ozon/msk.json --csv results/
    python ozon_price.py 1964684436 --cookies cookies/ozon/msk.json --proxy 1.2.3.4:8000:user:pass

Библиотека:
    from ozon_price import fetch_price
    r = fetch_price("1964684436", cookie_file="cookies/ozon/msk.json")
    print(r["price"], r["price_card"], r["price_base"])
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "fetch_price",
    "fetch_prices",
    "load_cookies",
    "normalize_proxy",
    "OzonError",
    "CookiesExpired",
    "PriceNotFound",
    "API_URL",
    "DEFAULT_IMPERSONATE",
    "O3_HEADERS",
]

API_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"

# Профили TLS curl_cffi: сначала generic alias, затем пиннутые версии.
# Ozon периодически ломает свежие профили — перебор спасает.
DEFAULT_IMPERSONATE: tuple[str, ...] = ("chrome", "chrome146", "chrome145", "chrome142", "chrome136")

# Заголовки клиента dweb (как в эталоне). x-o3-app-version / x-o3-manifest-version
# указывают на конкретную сборку фронта Ozon: со временем протухают.
# Если начнёт стабильно прилетать 400 — обнови их из DevTools (любой запрос к
# entrypoint-api.bx → Copy as cURL) или передай свои через параметр `headers`.
O3_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Content-Type": "application/json",
    "x-o3-app-name": "dweb_client",
    "x-o3-app-version": "release_24-6-2026_e801a3c6",
    "x-o3-manifest-version": (
        "frontend-ozon-ru:e801a3c62f8cfe341954419adfaa354dbaadf626,"
        "search-render-api:26877a5f1f6b92f5ef5a217ade8a0b151a885ecf,"
        "checkout-render-api:aecd1b3959ca8606f0af760c8123d37b48cc83e3,"
        "fav-render-api:59a97bd983119f6dddc92804adb6bad00256ce1b,"
        "pdp-render-api:c21f15997cdd645d082b0ef09089ca47e19990b7,"
        "sf-render-api:6b9533d13dc9cafbc4e33224af37432d468c316c"
    ),
}


class OzonError(RuntimeError):
    """Базовая ошибка чтения цены Ozon."""


class CookiesExpired(OzonError):
    """403 / антибот: куки протухли, либо запрос идёт не с того IP, где они снимались."""


class PriceNotFound(OzonError):
    """Ответ получен, но виджета цены в нём нет (снят с продажи / сменилась разметка)."""


# ──────────────────────────────────────────────────────────────────────
# Вход: куки и прокси
# ──────────────────────────────────────────────────────────────────────

def load_cookies(source: "str | Path | Sequence[dict[str, Any]] | dict[str, str]") -> dict[str, str]:
    """Привести куки к плоскому {name: value}.

    Принимает:
        * путь к JSON-списку кук (формат Playwright / расширений-экспортёров);
        * путь к storage_state.json (берётся ключ `cookies`);
        * путь к JSON-словарю {name: value};
        * уже готовый список/словарь.
    """
    if isinstance(source, dict):
        return {str(k): str(v) for k, v in source.items()}
    if isinstance(source, (list, tuple)):
        return {c["name"]: c["value"] for c in source}

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(
            f"Файл кук не найден: {path}\n"
            f"Сделай его один раз: python cookies_from_curl.py --out {path}"
        )
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("cookies", data)
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    if not data:
        raise OzonError(f"В {path} нет кук")
    return {c["name"]: c["value"] for c in data}


def normalize_proxy(raw: str | None) -> str | None:
    """`host:port:user:pass` / `host:port` / готовый URL → `http://user:pass@host:port`.

    Липкая сессия мобильного пула (`hold-session-session-<id>` у ASocks и аналогов)
    живёт внутри user-части и здесь не трогается — передавай логин целиком.
    """
    if not raw:
        return None
    raw = raw.strip()
    if "://" in raw:
        return raw
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    raise ValueError(f"Не понимаю формат прокси: {raw!r} (ожидаю host:port[:user:pass] или URL)")


# ──────────────────────────────────────────────────────────────────────
# Разбор ответа
# ──────────────────────────────────────────────────────────────────────

def _to_number(value: Any) -> float | None:
    """'2 682 ₽' (с узким пробелом) / '2682.00' / 2682 → 2682.0. Мусор → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) or None
    cleaned = re.sub(r"[^\d,.]", "", str(value)).replace(",", ".")
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return number if number > 0 else None


class WrongProductPage(OzonError):
    """Ответ пришёл не про тот товар (редирект/заглушка) — цену брать нельзя."""


class AmbiguousPrice(OzonError):
    """В ответе несколько разных виджетов цены и непонятно, какой принадлежит товару.

    Молча взять первый нельзя: в ответе живут карусели рекомендаций со своими
    webPrice, и первый попавшийся — цена ЧУЖОГО товара. Именно так эталон
    выдавал для одного sku 209 / 2805 / 9446 ₽ в соседних прогонах.
    """


def _widget_json(value: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _price_widget_from_layout(payload: dict[str, Any], states: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Найти виджет цены САМОГО товара через `layout`, а не перебором widgetStates.

    В `layout` перечислены компоненты страницы по порядку; у главного блока цены
    `component == "webPrice"`. Карусели рекомендаций там отдельными компонентами
    (`shelf`, `skuGrid`, …) и под этот фильтр не попадают.
    """
    layout = payload.get("layout")
    if not isinstance(layout, list):
        return None
    for component_name in ("webPrice", "webSale"):
        for block in layout:
            if not isinstance(block, dict) or block.get("component") != component_name:
                continue
            state_id = block.get("stateId")
            if not state_id or state_id not in states:
                continue
            widget = _widget_json(states[state_id])
            if widget and _to_number(widget.get("price")):
                return state_id, widget
    return None


def _check_page_matches_sku(payload: dict[str, Any], sku: str | int | None) -> None:
    """Убедиться, что ответ действительно про запрошенный товар."""
    if sku is None:
        return
    page_info = payload.get("pageInfo")
    url = page_info.get("url") if isinstance(page_info, dict) else None
    if not url:
        return
    if str(sku) not in str(url):
        raise WrongProductPage(
            f"Ozon вернул страницу {url!r}, а запрашивали /product/{sku}/ — "
            f"вероятно, редирект или заглушка. Цена не взята."
        )


def parse_widget_states(payload: dict[str, Any], sku: str | int | None = None) -> dict[str, Any]:
    """Достать цену из ответа entrypoint-api.

    Порядок доверия:
      1. виджет, на который указывает `layout` (это цена самого товара);
      2. если layout нет — перебор widgetStates, но при НЕСКОЛЬКИХ разных ценах
         поднимается AmbiguousPrice вместо тихого «взял первый».

    Никакого общего поиска по «₽» по телу ответа: он цепляет цены соседних
    товаров из рекомендаций и молча отдаёт чужое число.
    """
    states = payload.get("widgetStates") or {}
    if not states:
        raise CookiesExpired("В ответе нет widgetStates — обычно это антибот-заглушка")

    _check_page_matches_sku(payload, sku)
    unavailable = any("webOutOfStock" in k or "webNotFound" in k for k in states)

    def build(key: str, widget: dict[str, Any], trusted: bool) -> dict[str, Any]:
        price = _to_number(widget.get("price"))
        return {
            "price": price,
            "price_base": _to_number(widget.get("originalPrice")) or price,
            "price_card": _to_number(widget.get("cardPrice")),
            "is_available": bool(widget.get("isAvailable", True)) and not unavailable,
            "source": key.split("-")[0],
            "state_id": key,
            "trusted": trusted,  # True = виджет опознан через layout
            "raw": widget,
        }

    from_layout = _price_widget_from_layout(payload, states)
    if from_layout:
        return build(from_layout[0], from_layout[1], trusted=True)

    candidates: dict[str, dict[str, Any]] = {}
    for key, value in states.items():
        if "webPrice" not in key and "webSale" not in key:
            continue
        widget = _widget_json(value)
        if widget and _to_number(widget.get("price")):
            candidates[key] = widget

    if len(candidates) == 1:
        key, widget = next(iter(candidates.items()))
        return build(key, widget, trusted=False)

    if len(candidates) > 1:
        prices = {key: _to_number(w.get("price")) for key, w in candidates.items()}
        if len(set(prices.values())) == 1:  # все согласны — брать безопасно
            key, widget = next(iter(candidates.items()))
            return build(key, widget, trusted=False)
        raise AmbiguousPrice(
            f"В ответе {len(candidates)} разных цен и нет `layout`, чтобы выбрать нужную: {prices}. "
            f"Скорее всего, часть из них — карусель рекомендаций. Цена не взята."
        )

    if unavailable:
        return {
            "price": None,
            "price_base": None,
            "price_card": None,
            "is_available": False,
            "source": "webOutOfStock",
            "state_id": None,
            "trusted": True,
            "raw": {},
        }
    raise PriceNotFound(f"Виджет цены не найден. Виджеты в ответе: {sorted(states)[:12]}")


# ──────────────────────────────────────────────────────────────────────
# Запрос
# ──────────────────────────────────────────────────────────────────────

def fetch_payload(
    sku: str | int,
    *,
    cookie_file: "str | Path | Sequence[dict[str, Any]] | dict[str, str]",
    proxy: str | None = None,
    impersonate: Iterable[str] = DEFAULT_IMPERSONATE,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    verbose: bool = False,
    debug_dir: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Сходить в entrypoint-api и вернуть (сырой JSON, использованная стратегия).

    Отдельно от разбора — чтобы тем же запросом можно было проверить, какой город
    несут куки (см. `region_hints`).
    """
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as exc:  # pragma: no cover
        raise OzonError("curl_cffi не установлен: pip install curl-cffi") from exc

    cookies = load_cookies(cookie_file)
    proxies_arg = None
    proxy_url = normalize_proxy(proxy)
    if proxy_url:
        proxies_arg = {"http": proxy_url, "https": proxy_url}

    request_headers = dict(headers or O3_HEADERS)
    request_headers.setdefault("Referer", f"https://www.ozon.ru/product/{sku}/")
    params = {"url": f"/product/{sku}/"}

    last_status: int | None = None
    last_body: str = ""

    for target in impersonate:
        try:
            response = curl_requests.get(
                API_URL,
                params=params,
                headers=request_headers,
                cookies=cookies,
                impersonate=target,
                proxies=proxies_arg,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — сбой одной стратегии не фатален
            if verbose:
                print(f"   [{target}] сетевая ошибка: {exc}")
            continue

        last_status = response.status_code
        last_body = response.text or ""
        if verbose:
            print(f"   [{target}] HTTP {response.status_code}, {len(last_body)} б")

        if response.status_code != 200:
            continue
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001 — не JSON = антибот-страница
            continue

        return payload, target

    if debug_dir and last_body:
        dump_dir = Path(debug_dir)
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = dump_dir / f"ozon_{sku}_{int(time.time())}.txt"
        dump.write_text(last_body[:200_000], encoding="utf-8")
        if verbose:
            print(f"   дамп ответа: {dump}")

    if last_status in (401, 403):
        raise CookiesExpired(
            f"Ozon отвечает {last_status} на всех стратегиях. Куки протухли или запрос идёт "
            f"не с того IP, где они снимались. Обнови: python cookies_from_curl.py --out <файл>"
        )
    if last_status == 400:
        raise OzonError(
            "HTTP 400 — вероятно, протухли заголовки x-o3-app-version / x-o3-manifest-version. "
            "Обнови их из DevTools (Copy as cURL) в O3_HEADERS."
        )
    raise OzonError(f"Не удалось получить цену {sku} (последний статус: {last_status})")


def fetch_price(
    sku: str | int,
    *,
    cookie_file: "str | Path | Sequence[dict[str, Any]] | dict[str, str]",
    proxy: str | None = None,
    impersonate: Iterable[str] = DEFAULT_IMPERSONATE,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    verbose: bool = False,
    debug_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Прочитать цену товара Ozon одним запросом, без браузера.

    Args:
        sku: артикул из URL /product/<sku>/.
        cookie_file: путь к cookies.json (или готовые куки).
        proxy: `host:port:user:pass` / URL / None. Должен совпадать с IP, где снимались куки.
        impersonate: перебор профилей TLS curl_cffi.
        headers: переопределить заголовки x-o3-* целиком.
        debug_dir: куда сложить тело ответа при неудаче.

    Returns:
        {"sku", "price", "price_base", "price_card", "currency", "is_available",
         "source", "state_id", "trusted", "strategy", "raw"}

    Raises:
        CookiesExpired: 403 / антибот — нужны свежие куки с того же IP.
        AmbiguousPrice: несколько разных цен и нечем выбрать нужную.
        WrongProductPage: ответ про другой товар.
        PriceNotFound: ответ есть, цены нет.
        OzonError: прочие сбои.
    """
    payload, strategy = fetch_payload(
        sku,
        cookie_file=cookie_file,
        proxy=proxy,
        impersonate=impersonate,
        headers=headers,
        timeout=timeout,
        verbose=verbose,
        debug_dir=debug_dir,
    )
    result = parse_widget_states(payload, sku=sku)
    result.update(sku=str(sku), currency="RUB", strategy=strategy)
    if verbose and not result.get("trusted"):
        print(f"   ⚠️  виджет цены опознан без layout ({result.get('state_id')}) — сверь глазами")
    return result


def region_hints(payload: dict[str, Any]) -> dict[str, str]:
    """Вытащить из ответа всё, что намекает на город: адресная строка, сроки доставки, ПВЗ.

    Нужно, чтобы глазами убедиться: файл кук действительно несёт нужный город.
    Регион у Ozon привязан к сессии на его стороне, локально его не увидеть —
    только по тому, что он присылает в ответе.
    """
    states = payload.get("widgetStates") or {}
    interesting = ("address", "delivery", "pickup", "region", "location", "split")
    hints: dict[str, str] = {}
    for key, value in states.items():
        if not any(word in key.lower() for word in interesting):
            continue
        widget = _widget_json(value)
        if widget is None:
            continue
        text = json.dumps(widget, ensure_ascii=False)
        hints[key] = text[:400] + ("…" if len(text) > 400 else "")
    return hints


def show_region(
    sku: str | int,
    *,
    cookie_file: "str | Path | Sequence[dict[str, Any]] | dict[str, str]",
    proxy: str | None = None,
) -> dict[str, str]:
    """Показать, какой город несут куки — по адресным/доставочным виджетам ответа."""
    payload, _ = fetch_payload(sku, cookie_file=cookie_file, proxy=proxy)
    return region_hints(payload)


def fetch_prices(
    skus: Iterable[str | int],
    *,
    cookie_file: "str | Path | Sequence[dict[str, Any]] | dict[str, str]",
    proxy: str | None = None,
    pause: float = 1.5,
    verbose: bool = False,
    debug_dir: str | Path | None = None,
    stop_on_expired: bool = True,
) -> list[dict[str, Any]]:
    """Пройти по списку артикулов вежливым темпом. Ошибка по товару не роняет пачку.

    При `stop_on_expired` первая же CookiesExpired прекращает обход — дальше всё равно
    посыплется, и лучше не жечь лимиты.
    """
    results: list[dict[str, Any]] = []
    for index, sku in enumerate(skus):
        if index and pause:
            time.sleep(pause)
        try:
            results.append(
                fetch_price(
                    sku,
                    cookie_file=cookie_file,
                    proxy=proxy,
                    verbose=verbose,
                    debug_dir=debug_dir,
                )
            )
        except CookiesExpired as exc:
            results.append({"sku": str(sku), "error": "CookiesExpired", "message": str(exc)})
            if stop_on_expired:
                break
        except OzonError as exc:
            results.append({"sku": str(sku), "error": type(exc).__name__, "message": str(exc)})
    return results


def save_csv(results: Sequence[dict[str, Any]], out_dir: str | Path, region: str = "msk") -> Path | None:
    """Сохранить результаты в results/ozon_<region>_<timestamp>.csv."""
    import csv
    from datetime import datetime

    rows = [r for r in results if "price" in r]
    if not rows:
        return None
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ozon_{region}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    fields = ["sku", "price", "price_base", "price_card", "currency", "is_available", "source"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Цена Ozon без браузера (curl_cffi + куки)")
    parser.add_argument("sku", nargs="+", help="артикул(ы) Ozon")
    parser.add_argument("--cookies", required=True, help="путь к cookies.json")
    parser.add_argument("--proxy", default=None, help="host:port:user:pass или http://user:pass@host:port")
    parser.add_argument("--pause", type=float, default=1.5, help="пауза между товарами, сек")
    parser.add_argument("--region", default="msk", help="метка региона для имени CSV")
    parser.add_argument("--csv", default=None, help="папка для CSV с результатами")
    parser.add_argument("--debug-dir", default=None, help="куда сохранять тело ответа при неудаче")
    parser.add_argument("--json", action="store_true", help="вывести результат как JSON")
    parser.add_argument(
        "--show-region",
        action="store_true",
        help="не цену, а проверку: какой город несут эти куки (адрес/сроки доставки из ответа)",
    )
    parser.add_argument(
        "--find-mobile",
        action="store_true",
        help="перед замером покрутить session-id прокси, пока не выпадет мобильный IP (см. mobile_proxy.py)",
    )
    parser.add_argument("--mobile-tries", type=int, default=15, help="сколько session-id перебрать")
    args = parser.parse_args()

    if args.find_mobile:
        if not args.proxy:
            print("--find-mobile требует --proxy host:port:user:pass")
            return 1
        from mobile_proxy import find_mobile_session, is_mobile

        def _log(attempt: int, info: dict[str, Any] | None, sid: str) -> None:
            if info is None:
                print(f"  #{attempt} sid={sid}: проба не прошла")
                return
            mark = "← мобильный" if is_mobile(info.get("isp")) else "— не моб"
            print(f"  #{attempt} sid={sid}: {info['ip']} / {info.get('city')} / {info.get('isp')} {mark}")

        try:
            args.proxy = find_mobile_session(args.proxy, tries=args.mobile_tries, on_attempt=_log)
        except (RuntimeError, ValueError) as exc:
            print(f"❌ {exc}")
            return 1

    if args.show_region:
        hints = show_region(args.sku[0], cookie_file=args.cookies, proxy=args.proxy)
        if not hints:
            print("Адресных виджетов в ответе нет — город подтвердить нечем.")
            return 1
        print(f"Что Ozon отвечает по этим кукам (товар {args.sku[0]}):\n")
        for key, text in hints.items():
            print(f"  [{key}]\n    {text}\n")
        return 0

    results = fetch_prices(
        args.sku,
        cookie_file=args.cookies,
        proxy=args.proxy,
        pause=args.pause,
        verbose=not args.json,
        debug_dir=args.debug_dir,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            if "error" in result:
                print(f"{result['sku']}: ОШИБКА {result['error']} — {result['message']}")
                continue
            card = f", с картой {result['price_card']}" if result.get("price_card") else ""
            print(
                f"{result['sku']}: {result['price']} ₽ "
                f"(без скидки {result['price_base']}{card}) [{result['strategy']}]"
            )

    if args.csv:
        path = save_csv(results, args.csv, args.region)
        if path:
            print(f"CSV: {path}")

    return 1 if any("error" in r for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
