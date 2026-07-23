"""Run lifecycle (`run_once`) and the cron-driven `Scheduler` wrapper (ADR-0004, ADR-0009)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
from app.queue.factory import make_task_queue
from app.scheduler.retry import backoff_delay, is_retriable
from app.storage.base import (
    AttemptRepositoryProto,
    MeasureQueueRepositoryProto,
    PriceSnapshotRepositoryProto,
    ProductRepositoryProto,
    RegionRepositoryProto,
)
from app.storage.factory import StorageFactory

logger = logging.getLogger(__name__)

# Kept as the injectable-dependency type name across scripts/tests; now yields a
# `Storage` bundle (local or Postgres) rather than a raw SQLAlchemy session.
SessionFactory = StorageFactory


@dataclass(frozen=True)
class RunSummary:
    """Aggregated result of one full run."""

    run_id: int
    stats: dict[str, int]
    metrics: RunMetrics | None = None


async def _active_pairs(
    product_repo: ProductRepositoryProto, region_repo: RegionRepositoryProto
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
    product_repo: ProductRepositoryProto,
    region_repo: RegionRepositoryProto,
    queue_repo: MeasureQueueRepositoryProto,
    attempt_repo: AttemptRepositoryProto,
    snapshot_repo: PriceSnapshotRepositoryProto,
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
    storage_factory: SessionFactory,
    settings: Settings,
    semaphore: asyncio.Semaphore,
    interactive: bool,
    stats: dict[str, int],
    stats_lock: asyncio.Lock,
    pacer: RateLimiter,
) -> None:
    provider = make_proxy_provider(settings, storage_factory=storage_factory)
    cookie_store = make_cookie_store(settings)
    wb_collector = WbCollector()
    ozon_collector = OzonCollector(cookie_store)

    while True:
        async with semaphore:
            async with storage_factory() as storage:
                queue = make_task_queue(settings, storage)

                items = await queue.claim(settings.queue_claim_batch)
                await storage.commit()
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
                        product_repo=storage.products,
                        region_repo=storage.regions,
                        queue_repo=storage.queue_items,
                        attempt_repo=storage.attempts,
                        snapshot_repo=storage.snapshots,
                        pacer=pacer,
                    )
                    terminal_status = QueueStatus.DONE if outcome == Outcome.OK else QueueStatus.FAILED
                    await queue.complete(item, terminal_status)
                    await storage.commit()

                    async with stats_lock:
                        key = outcome.value if outcome is not None else "skipped"
                        stats[key] = stats.get(key, 0) + 1


async def run_once(
    storage_factory: SessionFactory,
    settings: Settings,
    *,
    mode: RunMode = RunMode.MANUAL,
    interactive: bool = False,
) -> RunSummary:
    """Create a run, enqueue all active pairs, drain the queue via a worker pool, finalize stats."""
    async with storage_factory() as storage:
        queue = make_task_queue(settings, storage)

        run = await storage.runs.create(mode=mode)
        pairs = await _active_pairs(storage.products, storage.regions)
        await queue.enqueue(run.id, [Pair(product_id=p, region_id=r) for p, r, _mp in pairs])
        await storage.commit()
        run_id = run.id

    logger.info("run.started", extra={"run_id": run_id, "mode": mode.value, "pairs": len(pairs)})

    stats: dict[str, int] = {}
    stats_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    pacer = make_rate_limiter(settings)

    workers = [
        _worker(storage_factory, settings, semaphore, interactive, stats, stats_lock, pacer)
        for _ in range(settings.max_concurrency)
    ]
    await asyncio.gather(*workers)

    async with storage_factory() as storage:
        finished_run = await storage.runs.get(run_id)
        if finished_run is not None:
            await storage.runs.finish(finished_run, RunStatus.DONE, stats)
        await storage.commit()

    async with storage_factory() as storage:
        metrics = await compute_run_metrics(storage, run_id)

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
    """Wraps an APScheduler `AsyncIOScheduler` that fires a job on `settings.schedule_cron`.

    Defaults to `run_once` for the job; pass `job` to fire a different pipeline
    callable instead (e.g. `app.scripts.orchestrator.run`), without duplicating
    the APScheduler wiring.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        job: Callable[[], Awaitable[RunSummary]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._scheduler = AsyncIOScheduler()
        self._job_fn = job or self._default_job

    def _default_job(self) -> Awaitable[RunSummary]:
        return run_once(self._session_factory, self._settings, mode=RunMode.SCHEDULED, interactive=False)

    def _job(self) -> Awaitable[RunSummary]:
        return self._job_fn()

    def start(self) -> None:
        """Register the cron job and start the scheduler."""
        trigger = CronTrigger.from_crontab(self._settings.schedule_cron)
        self._scheduler.add_job(self._job, trigger=trigger)
        self._scheduler.start()
        logger.info("scheduler started: cron=%s", self._settings.schedule_cron)

    def shutdown(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown()
