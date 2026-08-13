"""Мобильный прокси с липкой сессией — поиск мобильного IP БЕЗ браузера.

Оригинал (spike/check_ozon.py) делал то же самое, но каждую пробу гонял через
Playwright. Здесь пробы идут обычным curl_cffi — окон не открывается.

Зачем перебор
-------------
У ASocks и аналогов мобильный пул отдаётся под липкой сессией
(`hold-session-session-<id>`), но за одним ASN-фильтром лежат вперемешку мобильные
и обычные операторы — какой достанется, зависит от session-id. Поэтому крутим
session-id, проверяем оператора на лёгком сайте, и как поймали МОБИЛЬНЫЙ —
на этой же липкой сессии идём за ценой.

Ozon режет прокси по репутации IP: датацентровые и резидентные метит как VPN или
кидает капчу, мобильные (МТС/Билайн/МегаФон/Tele2/Yota) почти не трогает.

Использование
-------------
    # найти мобильный липкий IP и показать строку прокси
    python mobile_proxy.py --proxy host:port:user:pass --tries 15

    # найти и сразу прочитать цену через него
    python mobile_proxy.py --proxy host:port:user:pass --sku 1964684436 \
        --cookies cookies/ozon/msk.json

Из кода:
    from mobile_proxy import find_mobile_session
    proxy_url = find_mobile_session("host:port:user:pass", tries=15)
    from ozon_price import fetch_price
    fetch_price(sku, cookie_file="cookies/ozon/msk.json", proxy=proxy_url)

Важно: куки надо снимать через ТОТ ЖЕ прокси, иначе IP не совпадёт и прилетит 403.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Callable

__all__ = ["rotate_session", "probe_ip", "is_mobile", "find_mobile_session", "MOBILE_ISP"]

# Операторы, которые считаем мобильными (по строке ISP от ipwho.is)
MOBILE_ISP: tuple[str, ...] = (
    "mts",
    "vimpelcom",
    "beeline",
    "megafon",
    "tele2",
    "t2 mobile",
    "yota",
    "мтс",
    "билайн",
    "мегафон",
)

_PROBE_URL = "https://ipwho.is/"


def _split(raw: str) -> tuple[str, str, str | None, str | None]:
    """`host:port:user:pass` → кортеж. Принимает и `host:port`."""
    parts = raw.strip().split(":")
    if len(parts) == 4:
        return parts[0], parts[1], parts[2], parts[3]
    if len(parts) == 2:
        return parts[0], parts[1], None, None
    raise ValueError(f"Формат прокси: host:port:user:pass (получено {raw!r})")


def rotate_session(login: str, session_id: str) -> str:
    """Подставить новый session-id в логин — это и есть смена липкого IP.

    Понимает три формы логина: с `hold-query`, с уже проставленной
    `hold-session-session-<id>`, и голый логин без суффикса.
    """
    if "hold-query" in login:
        base = login.replace("hold-query", "").rstrip("-")
        return f"{base}-hold-session-session-{session_id}"
    if "hold-session-session-" in login:
        return re.sub(r"hold-session-session-.*$", f"hold-session-session-{session_id}", login)
    return f"{login}-hold-session-session-{session_id}"


def _proxy_url(host: str, port: str, user: str | None, password: str | None) -> str:
    if user:
        return f"http://{user}:{password}@{host}:{port}"
    return f"http://{host}:{port}"


def probe_ip(proxy_url: str, timeout: int = 20) -> dict[str, Any]:
    """Узнать, какой IP и оператор отдаёт прокси. Без браузера — обычный запрос."""
    try:
        from curl_cffi import requests as http
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("curl_cffi не установлен: pip install curl-cffi") from exc

    response = http.get(
        _PROBE_URL,
        impersonate="chrome",
        proxies={"http": proxy_url, "https": proxy_url},
        timeout=timeout,
    )
    data = response.json()
    connection = data.get("connection") or {}
    return {
        "ip": data.get("ip"),
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "isp": connection.get("isp") or connection.get("org"),
    }


def is_mobile(isp: str | None) -> bool:
    """Похож ли оператор на мобильного."""
    low = (isp or "").lower()
    return any(key in low for key in MOBILE_ISP)


def find_mobile_session(
    proxy: str,
    *,
    tries: int = 15,
    timeout: int = 20,
    on_attempt: Callable[[int, dict[str, Any] | None, str], None] | None = None,
) -> str:
    """Крутить session-id, пока не выпадет мобильный IP. Вернуть готовый URL прокси.

    Args:
        proxy: `host:port:user:pass` — логин с поддержкой липкой сессии.
        tries: сколько session-id перебрать.
        on_attempt: колбэк (номер попытки, инфо об IP или None, session_id) для логов.

    Raises:
        RuntimeError: за `tries` попыток мобильный IP не выпал.
    """
    host, port, user, password = _split(proxy)
    if not user:
        raise ValueError("Липкая сессия требует логин: host:port:user:pass")

    for attempt in range(1, tries + 1):
        session_id = secrets.token_hex(4)
        candidate = _proxy_url(host, port, rotate_session(user, session_id), password)
        try:
            info = probe_ip(candidate, timeout=timeout)
        except Exception:  # noqa: BLE001 — мобильные каналы моргают, пробуем следующий
            if on_attempt:
                on_attempt(attempt, None, session_id)
            continue
        if on_attempt:
            on_attempt(attempt, info, session_id)
        if is_mobile(info.get("isp")):
            return candidate

    raise RuntimeError(
        f"За {tries} попыток мобильный IP не выпал. Увеличь --tries или проверь, "
        f"что у прокси выбран mobile-тип/оператор."
    )


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Поиск мобильного липкого IP без браузера")
    parser.add_argument("--proxy", required=True, help="host:port:user:pass")
    parser.add_argument("--tries", type=int, default=15, help="сколько session-id перебрать")
    parser.add_argument("--sku", default=None, help="если задан — сразу прочитать цену через найденный прокси")
    parser.add_argument("--cookies", default=None, help="cookies.json (нужен вместе с --sku)")
    args = parser.parse_args()

    def log(attempt: int, info: dict[str, Any] | None, session_id: str) -> None:
        if info is None:
            print(f"  #{attempt} sid={session_id}: проба не прошла")
            return
        mark = "← МОБИЛЬНЫЙ, берём" if is_mobile(info.get("isp")) else "— не моб, меняю"
        print(f"  #{attempt} sid={session_id}: {info['ip']} / {info.get('city')} / {info.get('isp')}  {mark}")

    print(f"=== Автопоиск мобильного липкого IP (до {args.tries} попыток) ===")
    try:
        proxy_url = find_mobile_session(args.proxy, tries=args.tries, on_attempt=log)
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    masked = re.sub(r"//[^@]+@", "//***@", proxy_url)
    print(f"\n✅ Мобильный прокси найден: {masked}")

    if not args.sku:
        print("   Дальше: python ozon_price.py <sku> --cookies <файл> --proxy <этот URL>")
        return 0

    if not args.cookies:
        print("❌ Для --sku нужен ещё --cookies: без кук Ozon отдаёт 403 даже с мобильного IP")
        return 1

    from ozon_price import OzonError, fetch_price

    try:
        result = fetch_price(args.sku, cookie_file=args.cookies, proxy=proxy_url, verbose=True)
    except OzonError as exc:
        print(f"❌ {type(exc).__name__}: {exc}")
        return 1

    card = f", с картой {result['price_card']}" if result.get("price_card") else ""
    print(f"\n{result['sku']}: {result['price']} ₽ (без скидки {result['price_base']}{card})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
