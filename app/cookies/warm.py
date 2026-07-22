"""CookieWarmer — one-time manual captcha/city solve via Playwright (ADR-0005).

Productionizes `spike/check_ozon.py`: opens a real Chromium, lets the operator pass
the anti-bot challenge in `MANUAL=1` mode, and saves the resulting `storage_state`.
Headless/Xvfb warming on a server is Фаза 7 (ADR-0006) — not implemented here.
"""

import datetime
import logging
import os
from typing import Any, cast

from playwright.sync_api import sync_playwright

from app.cookies.base import CookieBundle, CookieStore, is_stale
from app.enums import Marketplace
from app.models import Region

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru']});
window.chrome={runtime:{}};
"""
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]

_MARKETPLACE_WARM_URL = {
    Marketplace.OZON: "https://www.ozon.ru/",
}


class CookieWarmer:
    """Opens a visible browser for the operator to solve the anti-bot challenge once."""

    def warm(self, marketplace: Marketplace, region: Region, proxy_url: str | None = None) -> CookieBundle:
        """Warm a fresh CookieBundle for (marketplace, region.code).

        `proxy_url`, if given, routes the browser through it — so warm-IP == fetch-IP
        for that city (hybrid model, ADR-0005). Runs in a visible browser (`MANUAL=1`
        is expected) so the operator can pass captcha / confirm the city.
        """
        warm_url = _MARKETPLACE_WARM_URL[marketplace]
        city = region.geo.get(marketplace.value, {}).get("city")
        proxy = {"server": proxy_url} if proxy_url else None
        manual = os.environ.get("MANUAL") == "1"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not manual, proxy=cast(Any, proxy), args=_LAUNCH_ARGS)
            try:
                ctx = browser.new_context(
                    user_agent=_USER_AGENT,
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                    viewport={"width": 1366, "height": 900},
                )
                ctx.add_init_script(_STEALTH_INIT_SCRIPT)
                page = ctx.new_page()
                page.goto(warm_url, wait_until="domcontentloaded", timeout=45000)
                if manual:
                    print(f"  Warming {marketplace.value}/{region.code} (city hint: {city}).")
                    print("  Solve the captcha / confirm the city in the browser window,")
                    print("  then return here and press Enter.")
                    try:
                        input("  >>> Enter once done... ")
                    except EOFError:
                        page.wait_for_timeout(30000)
                storage_state: dict[str, Any] = cast(Any, ctx.storage_state())
            finally:
                browser.close()

        return CookieBundle(
            marketplace=marketplace,
            region_code=region.code,
            storage_state=storage_state,
            warmed_at=datetime.datetime.now(datetime.UTC),
            stale=False,
            source_ref="static:proxy" if proxy_url else "direct",
        )


def warm_if_stale(
    store: CookieStore,
    warmer: CookieWarmer,
    marketplace: Marketplace,
    region: Region,
    ttl_hours: int,
    proxy_url: str | None = None,
) -> CookieBundle:
    """Return a fresh bundle for (marketplace, region), re-warming only if missing/stale."""
    bundle = store.load(marketplace, region.code)
    if bundle is not None and not is_stale(bundle, ttl_hours):
        return bundle
    fresh = warmer.warm(marketplace, region, proxy_url)
    store.save(fresh)
    logger.info("cookie warmed: marketplace=%s region=%s", marketplace.value, region.code)
    return fresh
