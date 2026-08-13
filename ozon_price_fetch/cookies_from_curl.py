"""Сделать cookies.json из строки кук — без запуска браузера из кода.

Разовый шаг. Дальше ozon_price.py работает сам, молча, без окон и без вопросов.

Откуда взять строку
-------------------
1. Открой ozon.ru в своём обычном Chrome, выбери нужный город (точку получения),
   зайди на любую карточку товара.
2. F12 → вкладка Network → любой запрос к `entrypoint-api.bx` →
   правый клик → Copy → **Copy as cURL (bash)**.
3. Вставь сюда — скрипт сам вытащит из cURL часть `-b '...'` / `-H 'cookie: ...'`.

Можно и короче: DevTools → Application → Cookies → ozon.ru → скопировать
пары `name=value; name=value; …`.

Запуск
------
    # из буфера обмена / вставкой в консоль (Ctrl+Z + Enter на Windows, Ctrl+D на Linux):
    python cookies_from_curl.py --out cookies/ozon/msk.json

    # из файла, куда вставил cURL:
    python cookies_from_curl.py --in curl.txt --out cookies/ozon/msk.json

Что важно
---------
* Куки живут примерно сутки — потом ozon_price.py кинет CookiesExpired, повтори этот шаг.
* Регион зашит в куке: сколько городов — столько файлов (msk.json, nvs.json, …).
* Читать цену надо с того же IP, где снимались куки. Если работаешь через прокси —
  снимай куки в браузере, поднятом через тот же прокси.
* В куках есть токены авторизации (`__Secure-access-token` и т.п.) — файл держи вне git.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# `-b 'a=1; b=2'` или `-H 'cookie: a=1; b=2'` в разных кавычках
_CURL_B = re.compile(r"-b\s+(['\"])(?P<jar>.*?)\1", re.DOTALL)
_CURL_H = re.compile(r"-H\s+(['\"])\s*cookie:\s*(?P<jar>.*?)\1", re.IGNORECASE | re.DOTALL)

# Куки, без которых Ozon обычно не отдаёт цену. Не жёсткая проверка — просто предупреждение.
_EXPECTED = ("__Secure-ext_xcid", "abt_data", "__Secure-ETC")


def extract_cookie_string(text: str) -> str:
    """Вытащить строку `name=value; …` из cURL-команды или принять её как есть."""
    for pattern in (_CURL_B, _CURL_H):
        match = pattern.search(text)
        if match:
            return match.group("jar").strip()
    if "=" in text and ";" in text:
        return text.strip()
    if "=" in text:
        return text.strip()
    raise SystemExit(
        "Не нашёл куки во вставленном тексте.\n"
        "Ожидаю либо целую команду cURL (Copy as cURL), либо строку вида 'a=1; b=2'."
    )


def parse_cookie_string(jar: str) -> list[dict[str, str]]:
    """`a=1; b=2` → [{'name': 'a', 'value': '1', 'domain': '.ozon.ru', 'path': '/'}, …]."""
    cookies: list[dict[str, str]] = []
    seen: set[str] = set()
    for chunk in jar.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name, value = name.strip(), value.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cookies.append({"name": name, "value": value, "domain": ".ozon.ru", "path": "/"})
    if not cookies:
        raise SystemExit("В строке не оказалось ни одной пары name=value")
    return cookies


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="cURL / строка кук → cookies.json для ozon_price.py")
    parser.add_argument("--out", required=True, help="куда записать, напр. cookies/ozon/msk.json")
    parser.add_argument("--in", dest="src", default=None, help="файл с cURL (по умолчанию — stdin)")
    args = parser.parse_args()

    if args.src:
        text = Path(args.src).read_text(encoding="utf-8")
    else:
        print("Вставь cURL или строку кук, затем Ctrl+Z+Enter (Windows) / Ctrl+D (Linux):")
        text = sys.stdin.read()

    cookies = parse_cookie_string(extract_cookie_string(text))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    names = {c["name"] for c in cookies}
    missing = [name for name in _EXPECTED if name not in names]
    print(f"✅ {len(cookies)} кук записано: {out}")
    if missing:
        print(f"⚠️  Не вижу привычных кук: {', '.join(missing)} — цена может не прийти.")
        print("   Проверь, что копировал запрос с ozon.ru после выбора точки получения.")
    print(f"   Проверка: python ozon_price.py <sku> --cookies {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
