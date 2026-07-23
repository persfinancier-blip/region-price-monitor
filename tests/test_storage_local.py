"""Local flat-file storage — every repo op round-trips through files, no DB (ADR-0009)."""

import datetime
import json
import os
from decimal import Decimal

from app.collectors.base import PriceObservation
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.storage.local import LocalStorage


async def test_product_upsert_round_trips_and_is_idempotent(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))

    first = await storage.products.upsert(
        marketplace=Marketplace.WB, sku="sku-1", url="https://example.com/1", name="A"
    )
    second = await storage.products.upsert(
        marketplace=Marketplace.WB, sku="sku-1", url="https://example.com/1", name="B"
    )

    assert first.id == second.id
    assert second.name == "B"

    fetched = await storage.products.get_by_id(first.id)
    assert fetched is not None
    assert fetched.name == "B"


async def test_product_list_active_excludes_inactive(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.products.upsert(marketplace=Marketplace.WB, sku="active", url="https://x/a", name="Active")
    await storage.products.upsert(
        marketplace=Marketplace.WB, sku="inactive", url="https://x/b", name="Inactive", is_active=False
    )

    active = await storage.products.list_active()
    skus = {p.sku for p in active}
    assert "active" in skus
    assert "inactive" not in skus


async def test_product_get_by_sku(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.products.upsert(marketplace=Marketplace.OZON, sku="oz-1", url="https://x/1", name="P")

    found = await storage.products.get_by_sku(marketplace=Marketplace.OZON, sku="oz-1")
    assert found is not None
    missing = await storage.products.get_by_sku(marketplace=Marketplace.WB, sku="oz-1")
    assert missing is None


async def test_region_upsert_round_trips_and_is_idempotent(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))

    first = await storage.regions.upsert(code="msk", name="Moscow", geo={"wb": {"dest": 1}})
    second = await storage.regions.upsert(code="msk", name="Moscow renamed", geo={"wb": {"dest": 1}})

    assert first.id == second.id
    assert second.name == "Moscow renamed"

    by_code = await storage.regions.get_by_code("msk")
    assert by_code is not None
    by_id = await storage.regions.get_by_id(first.id)
    assert by_id is not None
    assert by_id.code == "msk"


async def test_region_list_active_excludes_inactive(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.regions.upsert(code="msk", name="Moscow", geo={})
    await storage.regions.upsert(code="spb", name="SPB", geo={}, is_active=False)

    active = await storage.regions.list_active()
    codes = {r.code for r in active}
    assert codes == {"msk"}


async def test_run_lifecycle(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))

    run = await storage.runs.create(mode=RunMode.MANUAL)
    assert run.status == RunStatus.RUNNING
    assert run.finished_at is None

    fetched = await storage.runs.get(run.id)
    assert fetched is not None
    assert fetched.status == RunStatus.RUNNING

    finished = await storage.runs.finish(run, RunStatus.DONE, {"ok": 1})
    assert finished.status == RunStatus.DONE
    assert finished.stats == {"ok": 1}
    assert finished.finished_at is not None

    refetched = await storage.runs.get(run.id)
    assert refetched is not None
    assert refetched.status == RunStatus.DONE
    assert refetched.stats == {"ok": 1}


async def test_run_list_recent_orders_by_id_descending(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    first = await storage.runs.create(mode=RunMode.MANUAL)
    second = await storage.runs.create(mode=RunMode.SCHEDULED)
    third = await storage.runs.create(mode=RunMode.MANUAL)

    recent = await storage.runs.list_recent(2)
    assert [r.id for r in recent] == [third.id, second.id]
    assert first.id not in {r.id for r in recent}


async def test_snapshot_is_insert_only_and_serializes_decimal_as_string(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    obs = PriceObservation(
        price=Decimal("99.90"),
        price_base=Decimal("120.00"),
        price_card=Decimal("94.90"),
        currency="RUB",
        is_available=True,
        raw={"source": "test"},
    )

    snapshot = await storage.snapshots.add(product_id=1, region_id=2, run_id=3, obs=obs)

    assert snapshot.price == Decimal("99.90")
    assert snapshot.price_card == Decimal("94.90")

    snapshots_path = os.path.join(str(tmp_path), "snapshots.jsonl")
    with open(snapshots_path, encoding="utf-8") as fh:
        line = json.loads(fh.readline())
    assert isinstance(line["price"], str)
    assert isinstance(line["price_card"], str)

    all_snapshots = await storage.snapshots.list_all()
    assert len(all_snapshots) == 1
    assert all_snapshots[0].price == Decimal("99.90")


async def test_snapshot_price_card_none_round_trips(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    obs = PriceObservation(
        price=Decimal("10.00"),
        price_base=Decimal("10.00"),
        price_card=None,
        currency="RUB",
        is_available=True,
    )
    snapshot = await storage.snapshots.add(product_id=1, region_id=1, run_id=1, obs=obs)
    assert snapshot.price_card is None


async def test_queue_enqueue_claim_complete_lifecycle(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))

    item = await storage.queue_items.create(run_id=1, product_id=10, region_id=20)
    assert item.status == QueueStatus.PENDING
    assert item.attempts == 0

    claimed = await storage.queue_items.claim_pending(10)
    assert len(claimed) == 1
    assert claimed[0].status == QueueStatus.IN_PROGRESS
    assert claimed[0].locked_at is not None

    bumped = await storage.queue_items.increment_attempts(claimed[0])
    assert bumped.attempts == 1

    marked = await storage.queue_items.mark(claimed[0], QueueStatus.DONE)
    assert marked.status == QueueStatus.DONE

    refetched = await storage.queue_items.get(item.id)
    assert refetched is not None
    assert refetched.status == QueueStatus.DONE
    assert refetched.attempts == 1


async def test_queue_claim_pending_only_claims_pending_items(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.queue_items.create(run_id=1, product_id=1, region_id=1)
    await storage.queue_items.create(run_id=1, product_id=2, region_id=2)

    first_claim = await storage.queue_items.claim_pending(1)
    assert len(first_claim) == 1

    second_claim = await storage.queue_items.claim_pending(10)
    assert len(second_claim) == 1
    assert second_claim[0].id != first_claim[0].id


async def test_queue_reclaim_stale_returns_item_to_pending(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    item = await storage.queue_items.create(run_id=1, product_id=1, region_id=1)
    claimed = await storage.queue_items.claim_pending(10)
    assert claimed[0].id == item.id

    stale_threshold = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1)
    reclaimed_count = await storage.queue_items.reclaim_stale(stale_threshold)

    assert reclaimed_count == 1
    refetched = await storage.queue_items.get(item.id)
    assert refetched is not None
    assert refetched.status == QueueStatus.PENDING
    assert refetched.locked_at is None


async def test_queue_reclaim_stale_ignores_fresh_locks(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    item = await storage.queue_items.create(run_id=1, product_id=1, region_id=1)
    await storage.queue_items.claim_pending(10)

    threshold_in_the_past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1000)
    reclaimed_count = await storage.queue_items.reclaim_stale(threshold_in_the_past)

    assert reclaimed_count == 0
    refetched = await storage.queue_items.get(item.id)
    assert refetched is not None
    assert refetched.status == QueueStatus.IN_PROGRESS


async def test_attempt_is_insert_only_and_supports_recent_for_proxy_ref(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    now = datetime.datetime.now(datetime.UTC)

    await storage.attempts.add(
        queue_id=1, proxy_ref="static:msk:host", outcome=Outcome.HARD_BAN, duration_ms=100
    )
    await storage.attempts.add(queue_id=1, proxy_ref="static:msk:host", outcome=Outcome.OK, duration_ms=50)
    await storage.attempts.add(
        queue_id=1, proxy_ref="static:spb:other", outcome=Outcome.HARD_BAN, duration_ms=80
    )

    bans = await storage.attempts.recent_for_proxy_ref(
        "static:msk:host", since=now - datetime.timedelta(seconds=60), outcomes=(Outcome.HARD_BAN,)
    )
    assert len(bans) == 1
    assert bans[0].outcome == Outcome.HARD_BAN

    future_window = await storage.attempts.recent_for_proxy_ref(
        "static:msk:host", since=now + datetime.timedelta(seconds=60), outcomes=(Outcome.HARD_BAN,)
    )
    assert future_window == []


async def test_attempt_for_run_joins_via_queue_items(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))

    item_run1 = await storage.queue_items.create(run_id=1, product_id=1, region_id=1)
    item_run2 = await storage.queue_items.create(run_id=2, product_id=1, region_id=1)

    await storage.attempts.add(queue_id=item_run1.id, proxy_ref="x", outcome=Outcome.OK, duration_ms=10)
    await storage.attempts.add(queue_id=item_run1.id, proxy_ref="x", outcome=Outcome.ERROR, duration_ms=20)
    await storage.attempts.add(queue_id=item_run2.id, proxy_ref="x", outcome=Outcome.OK, duration_ms=30)

    run1_attempts = await storage.attempts.for_run(1)
    assert len(run1_attempts) == 2
    assert {a.outcome for a in run1_attempts} == {Outcome.OK, Outcome.ERROR}

    run2_attempts = await storage.attempts.for_run(2)
    assert len(run2_attempts) == 1


async def test_commit_is_a_noop(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.commit()  # must not raise


async def test_atomic_write_leaves_no_tmp_file_behind(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    await storage.products.upsert(marketplace=Marketplace.WB, sku="x", url="https://x/1", name="P")

    tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
    assert tmp_files == []
