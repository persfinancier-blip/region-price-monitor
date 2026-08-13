"""Разовый прогрев кук Ozon в настоящем браузере → cookies.json для ozon_price.py.

Браузер здесь нужен ровно один раз на регион (и потом раз в ~сутки, когда куки протухнут).
Рутинные замеры браузер не открывают вообще — их делает ozon_price.fetch_price().

Что критично (проверено на живых прогонах):
* Прогрев идёт в ВИДИМОМ браузере — капчу-пазл иначе не решить.
* Обязателен заход на карточку товара после выбора точки получения:
  без него сессия часто не считается «живой» и curl_cffi ловит 403.
* Регион зашит в куке (выбранная точка получения), не в IP.
  Один профиль = один город.
* Читать цену надо с того же IP, где грелись куки. Если греешь через прокси —
  тот же прокси передавай и в ozon_price.fetch_price().
* Закрой все окна Chrome перед запуском — иначе профиль залочен.

Запуск:
    python warm_cookies.py msk --sku 3129447770
    python warm_cookies.py spb --sku 3129447770 --proxy 1.2.3.4:8000:user:pass
"""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any

_HOME_URL = "https://www.ozon.ru/"
_PRODUCT_URL = "https://www.ozon.ru/product/{sku}/"
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--window-size=1920,1080",
]


def _kill_chrome() -> None:
    """Снять залипшие процессы Chrome — иначе persistent-профиль не откроется."""
    if platform.system() != "Windows":
        return
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001 — не критично
        pass


def _proxy_for_playwright(raw: str | None) -> dict[str, str] | None:
    """host:port:user:pass → {'server': ..., 'username': ..., 'password': ...}."""
    if not raw:
        return None
    raw = raw.strip()
    if "://" in raw:
        return {"server": raw}
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return {"server": f"http://{host}:{port}", "username": user, "password": password}
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    raise ValueError(f"Не понимаю формат прокси: {raw!r}")


def warm(
    region_code: str,
    *,
    sku: str | None = None,
    profiles_dir: str | Path = "profiles",
    proxy: str | None = None,
    headless: bool = False,
) -> Path:
    """Открыть Ozon, дать выбрать точку получения, зайти на карточку, сохранить cookies.json.

    Returns:
        Путь к сохранённому cookies.json.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Playwright не установлен:\n"
            "    pip install playwright\n"
            "    python -m playwright install chromium"
        ) from exc

    try:
        from playwright_stealth import stealth_sync
    except ImportError:
        stealth_sync = None  # работает и без stealth, просто чуть заметнее

    profile_dir = (Path(profiles_dir) / f"ozon_{region_code}").absolute()
    profile_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = profile_dir / "cookies.json"

    _kill_chrome()
    print(f"\n🌐 Прогрев Ozon, регион '{region_code}'")
    print(f"   Профиль: {profile_dir}")
    if proxy:
        print(f"   Через прокси: {proxy.split(':')[0]}:… (тот же прокси используй и при чтении цены)")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=_LAUNCH_ARGS,
            proxy=_proxy_for_playwright(proxy),
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        page = context.pages[0] if context.pages else context.new_page()
        if stealth_sync:
            stealth_sync(page)

        print("👉 Открываю ozon.ru…")
        page.goto(_HOME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        print("┌────────────────────────────────────────────────────────────")
        print("│ В открывшемся окне:")
        print("│  1) реши капчу-пазл, если появилась;")
        print(f"│  2) выбери ТОЧКУ ПОЛУЧЕНИЯ для региона '{region_code}';")
        print("│  3) вернись сюда и нажми Enter.")
        print("└────────────────────────────────────────────────────────────")
        try:
            input("   >>> Enter когда готово… ")
        except EOFError:
            page.wait_for_timeout(30000)

        # Заход на карточку — НЕ УБИРАТЬ. Без него сессия часто невалидна для curl_cffi.
        if sku:
            print(f"📦 Захожу на карточку {sku} — оживляю сессию…")
            page.goto(_PRODUCT_URL.format(sku=sku), wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            page.evaluate("window.scrollBy(0, 300)")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(1500)
        else:
            print("⚠️  --sku не задан: пропускаю заход на карточку. Куки могут не сработать.")

        cookies: list[dict[str, Any]] = context.cookies()
        cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        context.close()

    print(f"✅ Куки сохранены: {cookie_file}  ({len(cookies)} шт.)")
    print(f"   Проверка: python ozon_price.py {sku or '<sku>'} --cookies {cookie_file}")
    return cookie_file


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Разовый прогрев кук Ozon для ozon_price.py")
    parser.add_argument("region", help="код региона: msk, spb, nvs…  (это просто имя профиля)")
    parser.add_argument("--sku", default=None, help="артикул для захода на карточку (настоятельно рекомендуется)")
    parser.add_argument("--profiles-dir", default="profiles", help="куда класть профили (по умолчанию ./profiles)")
    parser.add_argument("--proxy", default=None, help="host:port:user:pass — если читать цену будешь через тот же прокси")
    args = parser.parse_args()

    warm(args.region, sku=args.sku, profiles_dir=args.profiles_dir, proxy=args.proxy)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
