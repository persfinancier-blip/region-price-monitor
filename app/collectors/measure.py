"""Shared per-pair measurement unit — used by the CLI and the worker pool alike."""

import asyncio
import logging
import time

import requests
from curl_cffi.requests.exceptions import RequestException as CurlRequestException

from app.collectors.base import PriceObservation
from app.collectors.outcome import classify_outcome
from app.collectors.ozon import OzonCollectionError, OzonCollector, OzonCookiesUnavailable
from app.collectors.wb import WbCollectionError, WbCollector
from app.config import Settings
from app.cookies.base import CookieStore
from app.cookies.base import is_stale as cookie_is_stale
from app.enums import Marketplace, Outcome
from app.models import Product, Region
from app.proxy.base import ProxyProvider
from app.repositories import AttemptRepository, PriceSnapshotRepository

logger = logging.getLogger(__name__)

# Sentinel returned when an Ozon pair needs cookie warming and is skipped
# without recording a fake attempt (the CLI's existing non-interactive rule).
NEEDS_WARM = None


async def measure_pair(
    *,
    run_id: int,
    product: Product,
    region: Region,
    provider: ProxyProvider,
    wb_collector: WbCollector,
    ozon_collector: OzonCollector,
    cookie_store: CookieStore,
    settings: Settings,
    interactive: bool,
    queue_id: int,
    snapshot_repo: PriceSnapshotRepository,
    attempt_repo: AttemptRepository,
) -> Outcome | None:
    """Run one (product, region) measurement attempt and return its Outcome.

    Reproduces the CLI's per-pair body exactly: acquire a lease, time the
    collection, classify the outcome, write a snapshot on OK, always write an
    attempts row, mark Ozon cookies stale on HARD_BAN, and report back to the
    provider. Returns `None` (no attempt written) when an Ozon pair needs
    cookie warming and isn't interactive — the caller marks the queue item
    without a fake attempt.
    """
    if product.marketplace == Marketplace.OZON and not interactive:
        bundle = cookie_store.load(Marketplace.OZON, region.code)
        if bundle is None or cookie_is_stale(bundle, settings.ozon_cookie_ttl_hours):
            return NEEDS_WARM

    lease = await provider.acquire(region.code)

    started = time.monotonic()
    status_code: int | None = None
    empty_products = False
    anti_bot = False
    error: str | None = None
    obs: PriceObservation | None = None
    exc_for_timeout: Exception | None = None

    try:
        if product.marketplace == Marketplace.WB:
            obs = await asyncio.to_thread(wb_collector.collect, product, region, lease.proxy_url)
        else:
            obs = await asyncio.to_thread(ozon_collector.collect, product, region, lease.proxy_url)
        status_code = 200
    except WbCollectionError as exc:
        status_code = exc.status_code
        empty_products = exc.empty_products
        error = str(exc)
    except OzonCookiesUnavailable:
        return NEEDS_WARM
    except OzonCollectionError as exc:
        status_code = exc.status_code
        anti_bot = exc.anti_bot
        error = str(exc)
    except (requests.Timeout, CurlRequestException) as exc:
        exc_for_timeout = exc
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 — classified below, never aborts the run
        exc_for_timeout = exc
        error = str(exc)
    duration_ms = int((time.monotonic() - started) * 1000)

    outcome = classify_outcome(
        status_code=status_code, exc=exc_for_timeout, empty_products=empty_products, anti_bot=anti_bot
    )

    if outcome == Outcome.OK and obs is not None:
        await snapshot_repo.add(product_id=product.id, region_id=region.id, run_id=run_id, obs=obs)
    if product.marketplace == Marketplace.OZON and outcome == Outcome.HARD_BAN:
        cookie_store.mark_stale(Marketplace.OZON, region.code)

    await attempt_repo.add(
        queue_id=queue_id, proxy_ref=lease.ref, outcome=outcome, duration_ms=duration_ms, error=error
    )
    await provider.report(lease, outcome)

    logger.info(
        "measurement",
        extra={
            "run_id": run_id,
            "marketplace": product.marketplace.value,
            "product_id": product.id,
            "sku": product.sku,
            "region_code": region.code,
            "proxy_ref": lease.ref,
            "outcome": outcome.value,
            "duration_ms": duration_ms,
            "error": error,
        },
    )

    return outcome
