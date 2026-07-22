"""Feasibility spike (part 3): Ozon price via REUSED browser cookies, no browser.

Идея: антибот-куки, честно добытые в обычном браузере, переиспользуем обычным
requests-запросом с ТВОЕГО IP (там куки валидны). Если Ozon отдаёт JSON с ценой —
значит связка «разово прогреть куки в браузере + дальше лёгкие запросы» рабочая.

Куки НЕ хранятся в коде. Положи строку куки (всё, что было внутри `-b '...'` в cURL)
в файл рядом: spike/ozon_cookie.txt  (он в .gitignore).

Запуск (с машины, где куки добывались — важно, IP должен совпадать):
    pip install requests
    python spike/check_ozon_cookies.py
    (другой товар: set OZON_PID=1234567890)
"""
from __future__ import annotations

import json
import os
import sys

# curl_cffi маскирует TLS/HTTP2-отпечаток под настоящий Chrome — без него Ozon
# блокирует запрос (403) даже с валидными куками. requests оставлен как фолбэк.
try:
    from curl_cffi import requests as http  # type: ignore
    _IMPERSONATE = True
except ImportError:  # noqa: BLE001
    import requests as http  # type: ignore
    _IMPERSONATE = False

HERE = os.path.dirname(os.path.abspath(__file__))
PID = os.environ.get("OZON_PID", "3129447770")
URL = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{PID}/"

HEADERS = {
    "accept": "application/json",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"),
    "referer": f"https://www.ozon.ru/product/{PID}/",
    "x-o3-app-name": "dweb_client",
    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


def load_cookie() -> str:
    env = os.environ.get("OZON_COOKIE", "").strip()
    if env:
        return env
    path = os.path.join(HERE, "ozon_cookie.txt")
    if not os.path.exists(path):
        sys.exit("ERROR: положи строку куки в spike/ozon_cookie.txt (или задай OZON_COOKIE)")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def find_price(data: dict) -> bool:
    states = data.get("widgetStates", {})
    hit = False
    for key, val in states.items():
        if "webPrice" in key or "webSale" in key:
            try:
                p = json.loads(val)
            except Exception:  # noqa: BLE001
                continue
            print(f"    [{key.split('-')[0]}] цена: {p.get('price')}  "
                  f"без карты: {p.get('originalPrice') or p.get('cardPrice')}  "
                  f"с Ozon-картой: {p.get('cardPrice') or p.get('price')}")
            hit = True
    if not hit:
        print(f"    цена в JSON не найдена; ключи виджетов: {list(states)[:8]}")
    return hit


def main() -> None:
    cookie = load_cookie()
    h = dict(HEADERS, cookie=cookie)
    mode = "curl_cffi (Chrome TLS)" if _IMPERSONATE else "requests (БЕЗ маскировки — вероятен 403)"
    print(f"=== Ozon цена по кукам (без браузера), товар {PID} ===")
    print(f"  движок: {mode}")
    kw = {"impersonate": "chrome"} if _IMPERSONATE else {}
    try:
        r = http.get(URL, headers=h, timeout=25, allow_redirects=True, **kw)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"  сетевой сбой: {e}")
    body = r.text or ""
    print(f"  HTTP {r.status_code}, {len(body)} б")
    if body.lstrip().startswith("{"):
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            print("  ответ не парсится как JSON — сохраняю в spike/ozon_cookie_dump.txt")
            _dump(body)
            return
        if find_price(data):
            print("  → РАБОТАЕТ: цена получена по кукам, без браузера и капчи.")
        else:
            _dump(json.dumps(data, ensure_ascii=False))
    else:
        head = body[:200].replace("\n", " ")
        print(f"  это не JSON (антибот/редирект?). начало: {head}")
        print("  Вероятная причина: куки протухли, или запрос ушёл не с того IP.")
        _dump(body)


def _dump(text: str) -> None:
    path = os.path.join(HERE, "ozon_cookie_dump.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  дамп: {path}")


if __name__ == "__main__":
    main()
