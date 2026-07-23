"""Run lifecycle (`run_once`) and the cron-driven `Scheduler` wrapper (ADR-0004)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.measure import measure_pair
from app.collectors.ozon import OzonCollector
from app.collectors.pacing import RateLimiter, make_rate_limiter
from app.collectors.wb import WbCollector
from app.config import Settings
from app.cookies.base import CookieStore
from app.cookies.fs import make_cookie_store
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.obs.alerts import Alert, make_alerter, should_alert
from app.obs.metrics import RunMetrics, compute_run_metrics
from app.proxy.base import ProxyProvider
from app.proxy.static import make_proxy_provider
from app.queue.base import Pair, QueueItem
from app.queue.postgres import make_task_queue
from app.repositories import (
    AttemptRepository,
    MeasureQueueRepository,
    PriceSnapshotRepository,
    ProductRepository,
    RegionRepository,
    RunRepository,
)
from app.scheduler.retry import backoff_delay, is_retriable

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class RunSummary:
    """Aggregated result of one full run."""

    run_id: int
    stats: dict[str, int]
    metrics: RunMetrics | None = None


async def _active_pairs(
    product_repo: ProductRepository, region_repo: RegionRepository
) -> list[tuple[int, int, Marketplace]]:
    """Active (product_id, region_id, marketplace) tuples.

    WB: all active regions. Ozon: active regions with an `ozon` geo entry.
    """
    products = await product_repo.list_active()
    regions = await region_repo.list_active()
    ozon_regions = [r for r in regions if "ozon" in r.geo]

    pairs: list[tuple[int, int, Marketplace]] = []
    for product in products:
        target_regions = regions if product.marketplace == Marketplace.WB else ozon_regions
        for region in target_regions:
            pairs.append((product.id, region.id, product.marketplace))
    return pairs


async def _process_item(
    item: QueueItem,
    *,
    settings: Settings,
    provider: ProxyProvider,
    wb_collector: WbCollector,
    ozon_collector: OzonCollector,
    cookie_store: CookieStore,
    interactive: bool,
    product_repo: ProductRepository,
    region_repo: RegionRepository,
    queue_repo: MeasureQueueRepository,
    attempt_repo: AttemptRepository,
    snapshot_repo: PriceSnapshotRepository,
    pacer: RateLimiter,
) -> Outcome | None:
    product = await product_repo.get_by_id(item.product_id)
    region = await region_repo.get_by_id(item.region_id)
    if product is None or region is None:
        return Outcome.ERROR

    attempt = 0
    outcome: Outcome | None = None
    while True:
        attempt += 1
        outcome = await measure_pair(
            run_id=item.run_id,
            product=product,
            region=region,
            provider=provider,
            wb_collector=wb_collector,
            ozon_collector=ozon_collector,
            cookie_store=cookie_store,
            settings=settings,
            interactive=interactive,
            queue_id=item.id,
            snapshot_repo=snapshot_repo,
            attempt_repo=attempt_repo,
            pacer=pacer,
        )
        if outcome is None:
            return None
        if not is_retriable(outcome) or attempt >= settings.retry_limit:
            return outcome
        queue_row = await queue_repo.get(item.id)
        if queue_row is not None:
            await queue_repo.increment_attempts(queue_row)
        delay = backoff_delay(attempt, settings.retry_backoff_base_s, settings.retry_backoff_max_s)
        await asyncio.sleep(delay)


async def _worker(
    session_factory: SessionFactory,
    settings: Settings,
    semaphore: asyncio.Semaphore,
    interactive: bool,
    stats: dict[str, int],
    stats_lock: asyncio.Lock,
    pacer: RateLimiter,
) -> None:
    provider = make_proxy_provider(settings, session_factory=session_factory)
    cookie_store = make_cookie_store(settings)
    wb_collector = WbCollector()
    ozon_collector = OzonCollector(cookie_store)

    while True:
        async with semaphore:
            async with session_factory() as session:
                queue = make_task_queue(session)
                product_repo = ProductRepository(session)
                region_repo = RegionRepository(session)
                queue_repo = MeasureQueueRepository(session)
                attempt_repo = AttemptRepository(session)
                snapshot_repo = PriceSnapshotRepository(session)

                items = await queue.claim(settings.queue_claim_batch)
                await session.commit()
                if not items:
                    return

                for item in items:
                    outcome = await _process_item(
                        item,
                        settings=settings,
                        provider=provider,
                        wb_collector=wb_collector,
                        ozon_collector=ozon_collector,
                        cookie_store=cookie_store,
                        interactive=interactive,
                        product_repo=product_repo,
                        region_repo=region_repo,
                        queue_repo=queue_repo,
                        attempt_repo=attempt_repo,
                        snapshot_repo=snapshot_repo,
                        pacer=pacer,
                    )
                    terminal_status = QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                    await queue.complete(item, terminal_status)
                    await session.commit()

                    async with stats_lock:
                        key = outcome.value if outcome is not None else "skipped"
                        stats[key] = stats.get(key, 0) + 1


async def run_once(
    session_factory: SessionFactory,
    settings: Settings,
    *,
    mode: RunMode = RunMode.MANUAL,
    interactive: bool = False,
) -> RunSummary:
    """Create a run, enqueue all active pairs, drain the queue via a worker pool, finalize stats."""
    async with session_factory() as session:
        run_repo = RunRepository(session)
        product_repo = ProductRepository(session)
        region_repo = RegionRepository(session)
        queue = make_task_queue(session)

        run = await run_repo.create(mode=mode)
        pairs = await _active_pairs(product_repo, region_repo)
        await queue.enqueue(run.id, [Pair(product_id=p, region_id=r) for p, r, _mp in pairs])
        await session.commit()
        run_id = run.id

    logger.info("run.started", extra={"run_id": run_id, "mode": mode.value, "pairs": len(pairs)})

    stats: dict[str, int] = {}
    stats_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    pacer = make_rate_limiter(settings)

    workers = [
        _worker(session_factory, settings, semaphore, interactive, stats, stats_lock, pacer)
        for _ in range(settings.max_concurrency)
    ]
    await asyncio.gather(*workers)

    async with session_factory() as session:
        run_repo = RunRepository(session)
        finished_run = await run_repo.get(run_id)
        if finished_run is not None:
            await run_repo.finish(finished_run, RunStatus.DONE, stats)
        await session.commit()

    async with session_factory() as session:
        metrics = await compute_run_metrics(session, run_id)

    logger.info(
        "run.finished",
        extra={
            "run_id": run_id,
            "total": metrics.total,
            "success_rate": metrics.success_rate,
            "ban_rate": metrics.ban_rate,
            "error_rate": metrics.error_rate,
            "avg_duration_ms": metrics.avg_duration_ms,
            "attempts_per_success": metrics.attempts_per_success,
        },
    )

    try:
        alerter = make_alerter(settings)
        if should_alert(metrics, settings.success_rate_threshold, settings.alert_min_measures):
            await alerter.send(
                Alert(
                    kind="success_rate_below_threshold",
                    run_id=run_id,
                    success_rate=metrics.success_rate,
                    threshold=settings.success_rate_threshold,
                    message=(
                        f"run {run_id}: success_rate={metrics.success_rate:.3f} "
                        f"below threshold={settings.success_rate_threshold}"
                    ),
                )
            )
    except Exception:  # noqa: BLE001 — alerting is best-effort, never fails the run
        logger.exception("alert delivery failed", extra={"run_id": run_id})

    return RunSummary(run_id=run_id, stats=stats, metrics=metrics)


class Scheduler:
    """Wraps an APScheduler `AsyncIOScheduler` that fires `run_once` on `settings.schedule_cron`."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._scheduler = AsyncIOScheduler()

    def _job(self) -> Awaitable[RunSummary]:
        return run_once(self._session_factory, self._settings, mode=RunMode.SCHEDULED, interactive=False)

    def start(self) -> None:
        """Register the cron job and start the scheduler."""
        trigger = CronTrigger.from_crontab(self._settings.schedule_cron)
        self._scheduler.add_job(self._job, trigger=trigger)
        self._scheduler.start()
        logger.info("scheduler started: cron=%s", self._settings.schedule_cron)

    def shutdown(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown()
