"""Full pipeline over the local backend, no Postgres: import -> run_once -> metrics/health."""

from decimal import Decimal
from unittest.mock import patch

from app.collectors.base import PriceObservation
from app.collectors.wb import WbCollector
from app.config import Settings
from app.enums import Marketplace, Outcome, RunMode, RunStatus
from app.obs.metrics import compute_run_metrics
from app.proxy.health import ProxyHealthService
from app.scheduler.runner import run_once
from app.scripts import control_panel, health
from app.storage.factory import make_storage


def _local_settings(tmp_path) -> Settings:
    return Settings(
        storage_backend="local",
        local_state_dir=str(tmp_path / "state"),
        max_concurrency=1,
        retry_limit=1,
        queue_claim_batch=10,
        proxy_health_enabled=False,
    )


async def test_import_then_run_once_writes_local_state_no_db(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    storage_factory = make_storage(settings)

    async with storage_factory() as storage:
        product = await storage.products.upsert(
            marketplace=Marketplace.WB, sku="local-e2e-sku", url="https://example.com/p", name="P"
        )
        region = await storage.regions.upsert(code="local-e2e-region", name="R", geo={"wb": {"dest": 1}})
        await storage.commit()

    obs = PriceObservation(
        price=Decimal("150.00"),
        price_base=Decimal("180.00"),
        price_card=Decimal("140.00"),
        currency="RUB",
        is_available=True,
    )

    with patch.object(WbCollector, "collect", return_value=obs):
        summary = await run_once(storage_factory, settings, mode=RunMode.MANUAL, interactive=False)

    assert summary.stats.get("ok") == 1
    assert summary.metrics is not None
    assert summary.metrics.success_rate == 1.0

    async with storage_factory() as storage:
        run_row = await storage.runs.get(summary.run_id)
        assert run_row is not None
        assert run_row.status == RunStatus.DONE

        snapshots = await storage.snapshots.list_all()
        matching = [s for s in snapshots if s.product_id == product.id and s.region_id == region.id]
        assert len(matching) == 1
        assert matching[0].price == Decimal("150.00")

        attempts = await storage.attempts.for_run(summary.run_id)
        assert len(attempts) == 1
        assert attempts[0].outcome == Outcome.OK


async def test_metrics_read_from_local_store(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    storage_factory = make_storage(settings)

    obs = PriceObservation(
        price=Decimal("10.00"),
        price_base=Decimal("10.00"),
        price_card=None,
        currency="RUB",
        is_available=True,
    )

    async with storage_factory() as storage:
        await storage.products.upsert(
            marketplace=Marketplace.WB, sku="metrics-e2e-sku", url="https://example.com/p", name="P"
        )
        await storage.regions.upsert(code="metrics-e2e-region", name="R", geo={"wb": {"dest": 1}})
        await storage.commit()

    with patch.object(WbCollector, "collect", return_value=obs):
        summary = await run_once(storage_factory, settings, mode=RunMode.MANUAL, interactive=False)

    async with storage_factory() as storage:
        metrics = await compute_run_metrics(storage, summary.run_id)

    assert metrics.total == 1
    assert metrics.success_rate == 1.0


async def test_health_report_reads_local_store_no_db(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    storage_factory = make_storage(settings)

    async with storage_factory() as storage:
        await storage.regions.upsert(code="health-e2e-region", name="R", geo={"ozon": {"city": "Moscow"}})
        await storage.commit()

    report = await health.run(fix=False, session_factory=storage_factory, settings=settings)

    assert len(report.regions) == 1
    assert report.regions[0].region_code == "health-e2e-region"
    # No warmed Ozon cookie exists yet in the tmp cookie dir -> stale/unhealthy.
    assert report.regions[0].cookie_stale is True


async def test_proxy_health_service_reads_recent_attempts_from_local_store(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    storage_factory = make_storage(settings)

    async with storage_factory() as storage:
        item = await storage.queue_items.create(run_id=1, product_id=1, region_id=1)
        for _ in range(3):
            await storage.attempts.add(
                queue_id=item.id, proxy_ref="static:msk:host", outcome=Outcome.HARD_BAN, duration_ms=50
            )
        await storage.commit()

    service = ProxyHealthService(storage_factory, settings.model_copy(update={"proxy_ban_threshold": 3}))
    verdict = await service.verdict("msk", "static:msk:host")

    assert verdict.cooling_down is True
    assert verdict.ban_count == 3


async def test_control_panel_show_reads_local_store_no_db(tmp_path) -> None:
    settings = _local_settings(tmp_path)
    storage_factory = make_storage(settings)

    async with storage_factory() as storage:
        await storage.products.upsert(
            marketplace=Marketplace.WB, sku="cp-e2e-sku", url="https://example.com/p", name="P"
        )
        await storage.regions.upsert(code="cp-e2e-region", name="R", geo={"wb": {"dest": 1}})
        await storage.commit()

    work_set = await control_panel.run(storage_factory, settings)

    assert len(work_set.pairs) == 1
    product, region, marketplace = work_set.pairs[0]
    assert product.sku == "cp-e2e-sku"
    assert region.code == "cp-e2e-region"
    assert marketplace == Marketplace.WB
