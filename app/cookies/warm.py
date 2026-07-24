"""CookieWarmer — one-time manual captcha/city solve via Playwright (ADR-0005, ADR-0012).

Productionizes `spike/check_ozon.py`: opens a real Chromium, lets the operator pass
the anti-bot challenge in `MANUAL=1` mode, and saves the resulting `storage_state`.
Headless/Xvfb warming on a server is Фаза 7 (ADR-0006) — not implemented here.

`warm_all` (ADR-0012, revised ADR-0013) adds the login-once + auto city-walk orchestration
used by the panel's «Куки» tab: one visible browser context, the operator solves the challenge
once, then the flow walks the configured cities unattended — WB a single session (region rides
the proxy), pausing only on captcha. Ozon's region is baked into the cookie set, written only
when a delivery address is chosen in the UI (ADR-0013) — there is no `?city=` shortcut: a city
with no remembered address is captured guided (operator picks the address once, we remember the
label); a city with a remembered address is auto-repaired by re-selecting it from the account's
address book.
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

_OZON_ADDRESS_TRIGGER_SELECTOR = "[data-widget='header'] [data-widget='skeletonLayout']"
_OZON_ADDRESS_LABEL_SELECTOR = "[data-widget='linkRegion'], [data-widget='header'] address"
_OZON_ADDRESS_BOOK_ITEM_SELECTOR = "[data-widget='addressBookItem'], li[data-address-id]"
_ADDRESS_POLL_S = 1.0


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
    address_label: str | None = None
    """Remembered Ozon delivery address for this city (ADR-0013); `None` ⇒ guided capture."""


@dataclass(frozen=True)
class WalkStepResult:
    """Outcome of one city step during the walk — reported back for panel progress."""

    city_code: str
    status: str  # "saved" | "skipped" | "timeout" | "cancelled"
    detail: str | None = None
    address_label: str | None = None
    """The address_label captured/selected for this step, when status == "saved"."""


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


class AddressCaptureError(Exception):
    """Raised when the guided/auto address flow can't complete — triggers a guided fallback."""


def _read_ozon_address_label(page: Page) -> str | None:
    """Best-effort read of the currently selected delivery address label from the page."""
    try:
        locator = page.locator(_OZON_ADDRESS_LABEL_SELECTOR).first
        if locator.count() == 0:
            return None
        text = locator.inner_text(timeout=5000).strip()
        return text or None
    except Exception:  # pragma: no cover - defensive, real-browser only
        return None


def _capture_ozon_address(page: Page, city: WalkCity, *, timeout_s: float, cancel: CancelToken | None) -> str:
    """Guided capture: the operator picks/confirms the delivery address in the visible browser.

    Ozon does **not** take the region from a `?city=` query — the region is baked into the
    cookie set when a delivery address is chosen in the UI (ADR-0013). This polls the page for
    an address label to appear/change rather than blocking on a console `input()`, so the flow
    stays drivable from the panel; the operator does the actual click in the browser window.
    """
    page.goto(_MARKETPLACE_WARM_URL[Marketplace.OZON], wait_until="domcontentloaded", timeout=45000)
    deadline = time.monotonic() + timeout_s
    label = _read_ozon_address_label(page)
    while not label:
        if cancel is not None and cancel.is_set():
            raise AddressCaptureError(f"cancelled while waiting for address pick ({city.code})")
        if time.monotonic() >= deadline:
            raise AddressCaptureError(f"timed out waiting for the operator to pick an address ({city.code})")
        page.wait_for_timeout(int(_ADDRESS_POLL_S * 1000))
        label = _read_ozon_address_label(page)
    return label


def _select_saved_address(page: Page, city: WalkCity, *, timeout_s: float, cancel: CancelToken | None) -> str:
    """Auto-select: drive Ozon's address book to the remembered `address_label` for this city.

    The exact address-book DOM/API is empirically uncertain (ADR-0013) — this stays defensive:
    any failure to locate/select the remembered label raises `AddressCaptureError`, which the
    caller turns into a guided-fallback step rather than a silent wrong-region save.
    """
    if not city.address_label:
        raise AddressCaptureError(f"no remembered address for {city.code}")
    page.goto(_MARKETPLACE_WARM_URL[Marketplace.OZON], wait_until="domcontentloaded", timeout=45000)

    trigger = page.locator(_OZON_ADDRESS_TRIGGER_SELECTOR).first
    try:
        if trigger.count() > 0:
            trigger.click(timeout=5000)
    except Exception as exc:  # pragma: no cover - defensive, real-browser only
        raise AddressCaptureError(f"could not open address picker for {city.code}: {exc}") from exc

    deadline = time.monotonic() + timeout_s
    entry = page.locator(_OZON_ADDRESS_BOOK_ITEM_SELECTOR, has_text=city.address_label).first
    while entry.count() == 0:
        if cancel is not None and cancel.is_set():
            raise AddressCaptureError(f"cancelled while selecting saved address ({city.code})")
        if time.monotonic() >= deadline:
            raise AddressCaptureError(f"remembered address not found in address book ({city.code})")
        page.wait_for_timeout(int(_ADDRESS_POLL_S * 1000))
        entry = page.locator(_OZON_ADDRESS_BOOK_ITEM_SELECTOR, has_text=city.address_label).first

    try:
        entry.click(timeout=5000)
    except Exception as exc:  # pragma: no cover - defensive, real-browser only
        raise AddressCaptureError(f"could not click the saved address for {city.code}: {exc}") from exc

    label = _read_ozon_address_label(page) or city.address_label
    return label


def _save_bundle(
    store: CookieStore,
    marketplace: Marketplace,
    region_code: str,
    storage_state: dict[str, Any],
    *,
    address_label: str | None = None,
) -> None:
    store.save(
        CookieBundle(
            marketplace=marketplace,
            region_code=region_code,
            storage_state=storage_state,
            warmed_at=datetime.datetime.now(datetime.UTC),
            stale=False,
            source_ref="warm_all",
            address_label=address_label,
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

    Ozon: iterate `cities`; a city with an `address_label` is auto-repaired by re-selecting
    that saved address, a city without one is captured guided (operator picks the address,
    label is remembered); either way saves a per-(ozon, city) `CookieBundle` with the label
    attached (ADR-0013). WB: warm a single session bundle under `_WB_SESSION_REGION` — region
    rides the proxy, not the cookie, so there is nothing to walk per city; the button stays
    symmetric with an honest single-pass no-op-shaped record. Pauses only on captcha
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
                if city.address_label:
                    label = _select_saved_address(page, city, timeout_s=step_timeout_s, cancel=cancel)
                else:
                    label = _capture_ozon_address(page, city, timeout_s=step_timeout_s, cancel=cancel)
                if _looks_like_captcha(page):
                    cleared = _wait_out_captcha(page, timeout_s=step_timeout_s, cancel=cancel)
                    if not cleared:
                        results.append(WalkStepResult(city.code, "timeout", "captcha did not clear"))
                        if on_progress:
                            on_progress(city.code, "timeout", "captcha did not clear")
                        continue
                storage_state = cast(Any, ctx.storage_state())
            except AddressCaptureError as exc:
                results.append(WalkStepResult(city.code, "skipped", str(exc)))
                if on_progress:
                    on_progress(city.code, "skipped", str(exc))
                continue
            except Exception as exc:  # pragma: no cover - defensive, real-browser only
                results.append(WalkStepResult(city.code, "skipped", str(exc)))
                if on_progress:
                    on_progress(city.code, "skipped", str(exc))
                continue

            _save_bundle(store, marketplace, city.code, storage_state, address_label=label)
            results.append(WalkStepResult(city.code, "saved", address_label=label))
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
