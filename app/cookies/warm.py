"""CookieWarmer — one-time manual captcha/city solve via Playwright (ADR-0005, ADR-0012).

Productionizes `spike/check_ozon.py`: opens a real Chromium, lets the operator pass
the anti-bot challenge in `MANUAL=1` mode, and saves the resulting `storage_state`.
Headless/Xvfb warming on a server is Фаза 7 (ADR-0006) — not implemented here.

`warm_all` (ADR-0012) adds the login-once + auto city-walk orchestration used by the
panel's «Куки» tab: one visible browser context, the operator solves the challenge once,
then the flow walks the configured cities unattended — Ozon per-city (region baked into
the cookie), WB a single session (region rides the proxy) — pausing only on captcha.
"""

import datetime
import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from playwright.sync_api import BrowserContext, Page, sync_playwright

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
    Marketplace.WB: "https://www.wildberries.ru/",
}

_CAPTCHA_MARKERS = ("captcha", "проверка", "подтвердите, что вы не робот")
_CAPTCHA_POLL_S = 2.0
_WB_SESSION_REGION = "_session"


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


@dataclass(frozen=True)
class WalkCity:
    """One city to walk during `warm_all` — decoupled from `app.scripts.cities`."""

    code: str
    name: str
    geo: dict[str, Any]
    proxy_url: str | None = None


@dataclass(frozen=True)
class WalkStepResult:
    """Outcome of one city step during the walk — reported back for panel progress."""

    city_code: str
    status: str  # "saved" | "skipped" | "timeout" | "cancelled"
    detail: str | None = None


class ProgressReporter(Protocol):
    """Callback invoked after each step of the walk — drives the panel's live progress."""

    def __call__(self, city_code: str, status: str, detail: str | None = None) -> None: ...


class CancelToken(Protocol):
    """Cooperative cancel/skip signal so a stuck city can't hang the walk."""

    def is_set(self) -> bool: ...


def _looks_like_captcha(page: Page) -> bool:
    try:
        text = page.content().lower()
    except Exception:  # pragma: no cover - defensive, page may be mid-navigation
        return False
    return any(marker in text for marker in _CAPTCHA_MARKERS)


def _wait_out_captcha(page: Page, *, timeout_s: float, cancel: CancelToken | None) -> bool:
    """Poll until the captcha marker disappears from the page, or timeout/cancel fires.

    Returns True if the page cleared, False on timeout/cancel — never blocks on `input()`
    so the flow stays drivable from the panel (no terminal attached).
    """
    deadline = time.monotonic() + timeout_s
    while _looks_like_captcha(page):
        if cancel is not None and cancel.is_set():
            return False
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(int(_CAPTCHA_POLL_S * 1000))
    return True


def _switch_ozon_city(page: Page, city: WalkCity) -> None:
    """Auto-switch Ozon's delivery city via its region cookie/param.

    Ozon bakes the region into the cookie (ADR-0005) — re-visiting with a `city` query
    hint (falling back to the plain city name) is enough to rewrite that cookie without
    a manual city-selector click.
    """
    city_hint = city.geo.get(Marketplace.OZON.value, {}).get("city") or city.name
    url = f"{_MARKETPLACE_WARM_URL[Marketplace.OZON]}?city={city_hint}"
    page.goto(url, wait_until="domcontentloaded", timeout=45000)


def _save_bundle(
    store: CookieStore, marketplace: Marketplace, region_code: str, storage_state: dict[str, Any]
) -> None:
    store.save(
        CookieBundle(
            marketplace=marketplace,
            region_code=region_code,
            storage_state=storage_state,
            warmed_at=datetime.datetime.now(datetime.UTC),
            stale=False,
            source_ref="warm_all",
        )
    )


def warm_all(
    store: CookieStore,
    marketplace: Marketplace,
    cities: Iterable[WalkCity],
    *,
    step_timeout_s: float = 60.0,
    cancel: CancelToken | None = None,
    on_progress: ProgressReporter | None = None,
    launch_browser: Callable[[], tuple[Any, BrowserContext]] | None = None,
) -> list[WalkStepResult]:
    """Login-once + auto city-walk: one visible browser context for the whole walk.

    Ozon: iterate `cities`, auto-switch the delivery city per step, save a per-(ozon, city)
    `CookieBundle` to `store`. WB: warm a single session bundle under `_WB_SESSION_REGION` —
    region rides the proxy, not the cookie, so there is nothing to walk per city; the button
    stays symmetric with an honest single-pass no-op-shaped record. Pauses only on captcha
    (auto-detected, polled) — never blocks on console `input()`. Each step has its own timeout
    and honours `cancel` so a stuck city can't hang the whole walk.

    `launch_browser` is an injection seam for tests (avoids a real Playwright/Chromium in CI);
    it must return `(browser, context)` with the context already navigated/logged-in.
    """
    cities = list(cities)
    manual = os.environ.get("MANUAL") == "1"
    results: list[WalkStepResult] = []

    def _default_launch() -> tuple[Any, BrowserContext]:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not manual, args=_LAUNCH_ARGS)
        ctx = browser.new_context(
            user_agent=_USER_AGENT,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 900},
        )
        ctx.add_init_script(_STEALTH_INIT_SCRIPT)
        return browser, ctx

    launch_browser = launch_browser or _default_launch
    browser, ctx = launch_browser()
    try:
        page = ctx.new_page()
        page.goto(_MARKETPLACE_WARM_URL[marketplace], wait_until="domcontentloaded", timeout=45000)
        if _looks_like_captcha(page):
            cleared = _wait_out_captcha(page, timeout_s=step_timeout_s, cancel=cancel)
            if not cleared:
                result = WalkStepResult("_login", "timeout", "captcha did not clear on login")
                results.append(result)
                if on_progress:
                    on_progress(result.city_code, result.status, result.detail)
                return results

        if marketplace is Marketplace.WB:
            storage_state: dict[str, Any] = cast(Any, ctx.storage_state())
            _save_bundle(store, marketplace, _WB_SESSION_REGION, storage_state)
            results.append(WalkStepResult(_WB_SESSION_REGION, "saved"))
            if on_progress:
                on_progress(_WB_SESSION_REGION, "saved")
            return results

        for city in cities:
            if cancel is not None and cancel.is_set():
                results.append(WalkStepResult(city.code, "cancelled"))
                if on_progress:
                    on_progress(city.code, "cancelled")
                continue
            try:
                _switch_ozon_city(page, city)
                if _looks_like_captcha(page):
                    cleared = _wait_out_captcha(page, timeout_s=step_timeout_s, cancel=cancel)
                    if not cleared:
                        results.append(WalkStepResult(city.code, "timeout", "captcha did not clear"))
                        if on_progress:
                            on_progress(city.code, "timeout", "captcha did not clear")
                        continue
                storage_state = cast(Any, ctx.storage_state())
            except Exception as exc:  # pragma: no cover - defensive, real-browser only
                results.append(WalkStepResult(city.code, "skipped", str(exc)))
                if on_progress:
                    on_progress(city.code, "skipped", str(exc))
                continue

            _save_bundle(store, marketplace, city.code, storage_state)
            results.append(WalkStepResult(city.code, "saved"))
            if on_progress:
                on_progress(city.code, "saved")
    finally:
        browser.close()

    return results


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
