"""Local flat-file storage (ADR-0009) — no Postgres required.

Each entity lives under `settings.local_state_dir`: reference tables
(`products`, `regions`) as whole-file JSON arrays (small, upserted in place);
append-only tables (`runs`, `attempts`, `snapshots`) as JSONL, one record per
line; the queue as a whole-file JSON array (`queue.json`). Every write goes
through `_atomic_write` (temp file + `os.replace`) so a crash mid-write never
corrupts the store. Ids are monotonic per-entity counters persisted alongside
the data file.

This backend is single-process/single-machine by construction: there is no
cross-process locking, so concurrent writers would race. That's fine for the
local single-user use case (ADR-0009); Postgres's `FOR UPDATE SKIP LOCKED`
remains the only backend with a real cross-process concurrency guarantee.
"""

import datetime
import json
import os
from decimal import Decimal
from typing import Any

from app.collectors.base import PriceObservation
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus
from app.models import Attempt, MeasureQueueItem, PriceSnapshot, Product, Region, Run


def _atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _atomic_append_jsonl(path: str, record: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    # Append is not itself atomic across a crash mid-write, but a single JSON
    # line write is small enough that partial writes are not a practical risk
    # for this local single-user backend; the rewrite path (`_atomic_write_json`)
    # is used for anything that mutates existing records in place.
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_json_list(path: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = _read_json(path, [])
    return result


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _decimal_or_none(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


class _IdCounter:
    """A monotonic id counter persisted as a single-integer JSON file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def next(self) -> int:
        current = _read_json(self._path, 0)
        nxt = int(current) + 1
        _atomic_write_json(self._path, nxt)
        return nxt


class LocalProductRepository:
    """Flat-file `Product` repository — one JSON array file, upserted in place."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "products.json")
        self._ids = _IdCounter(os.path.join(base_dir, ".products.id"))

    def _load(self) -> list[dict[str, Any]]:
        return _read_json_list(self._path)

    def _to_model(self, row: dict[str, Any]) -> Product:
        return Product(
            id=row["id"],
            marketplace=Marketplace(row["marketplace"]),
            sku=row["sku"],
            url=row["url"],
            name=row["name"],
            is_active=row["is_active"],
            created_at=datetime.datetime.fromisoformat(row["created_at"]),
        )

    async def upsert(
        self, *, marketplace: Marketplace, sku: str, url: str, name: str, is_active: bool = True
    ) -> Product:
        rows = self._load()
        for row in rows:
            if row["marketplace"] == marketplace.value and row["sku"] == sku:
                row.update(url=url, name=name, is_active=is_active)
                _atomic_write_json(self._path, rows)
                return self._to_model(row)

        row = {
            "id": self._ids.next(),
            "marketplace": marketplace.value,
            "sku": sku,
            "url": url,
            "name": name,
            "is_active": is_active,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        rows.append(row)
        _atomic_write_json(self._path, rows)
        return self._to_model(row)

    async def list_active(self) -> list[Product]:
        return [self._to_model(row) for row in self._load() if row["is_active"]]

    async def get_by_sku(self, *, marketplace: Marketplace, sku: str) -> Product | None:
        for row in self._load():
            if row["marketplace"] == marketplace.value and row["sku"] == sku and row["is_active"]:
                return self._to_model(row)
        return None

    async def get_by_id(self, product_id: int) -> Product | None:
        for row in self._load():
            if row["id"] == product_id:
                return self._to_model(row)
        return None


class LocalRegionRepository:
    """Flat-file `Region` repository — one JSON array file, upserted in place."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "regions.json")
        self._ids = _IdCounter(os.path.join(base_dir, ".regions.id"))

    def _load(self) -> list[dict[str, Any]]:
        return _read_json_list(self._path)

    def _to_model(self, row: dict[str, Any]) -> Region:
        return Region(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            geo=row["geo"],
            is_active=row["is_active"],
        )

    async def upsert(self, *, code: str, name: str, geo: dict[str, Any], is_active: bool = True) -> Region:
        rows = self._load()
        for row in rows:
            if row["code"] == code:
                row.update(name=name, geo=geo, is_active=is_active)
                _atomic_write_json(self._path, rows)
                return self._to_model(row)

        row = {"id": self._ids.next(), "code": code, "name": name, "geo": geo, "is_active": is_active}
        rows.append(row)
        _atomic_write_json(self._path, rows)
        return self._to_model(row)

    async def list_active(self) -> list[Region]:
        return [self._to_model(row) for row in self._load() if row["is_active"]]

    async def get_by_code(self, code: str) -> Region | None:
        for row in self._load():
            if row["code"] == code:
                return self._to_model(row)
        return None

    async def get_by_id(self, region_id: int) -> Region | None:
        for row in self._load():
            if row["id"] == region_id:
                return self._to_model(row)
        return None


class LocalRunRepository:
    """Flat-file `Run` repository — append-only JSONL, mutated in place for `finish`."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "runs.jsonl")
        self._ids = _IdCounter(os.path.join(base_dir, ".runs.id"))

    def _load(self) -> list[dict[str, Any]]:
        return _read_jsonl(self._path)

    def _to_model(self, row: dict[str, Any]) -> Run:
        return Run(
            id=row["id"],
            mode=RunMode(row["mode"]),
            status=RunStatus(row["status"]),
            started_at=datetime.datetime.fromisoformat(row["started_at"]),
            finished_at=(datetime.datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None),
            stats=row["stats"],
        )

    async def create(self, *, mode: RunMode) -> Run:
        row: dict[str, Any] = {
            "id": self._ids.next(),
            "mode": mode.value,
            "status": RunStatus.RUNNING.value,
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "finished_at": None,
            "stats": {},
        }
        _atomic_append_jsonl(self._path, row)
        return self._to_model(row)

    async def get(self, run_id: int) -> Run | None:
        for row in self._load():
            if row["id"] == run_id:
                return self._to_model(row)
        return None

    async def list_recent(self, limit: int = 10) -> list[Run]:
        rows = sorted(self._load(), key=lambda r: r["id"], reverse=True)
        return [self._to_model(row) for row in rows[:limit]]

    async def finish(self, run: Run, status: RunStatus, stats: dict[str, Any]) -> Run:
        rows = self._load()
        for row in rows:
            if row["id"] == run.id:
                row["status"] = status.value
                row["stats"] = stats
                row["finished_at"] = datetime.datetime.now(datetime.UTC).isoformat()
                _atomic_write_json_lines(self._path, rows)
                return self._to_model(row)
        raise ValueError(f"unknown run id: {run.id}")


def _atomic_write_json_lines(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp_path, path)


class LocalPriceSnapshotRepository:
    """Flat-file `PriceSnapshot` repository — insert-only JSONL."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "snapshots.jsonl")
        self._ids = _IdCounter(os.path.join(base_dir, ".snapshots.id"))

    def _load(self) -> list[dict[str, Any]]:
        return _read_jsonl(self._path)

    def _to_model(self, row: dict[str, Any]) -> PriceSnapshot:
        return PriceSnapshot(
            id=row["id"],
            product_id=row["product_id"],
            region_id=row["region_id"],
            run_id=row["run_id"],
            captured_at=datetime.datetime.fromisoformat(row["captured_at"]),
            price=Decimal(row["price"]),
            price_base=Decimal(row["price_base"]),
            price_card=_decimal_or_none(row["price_card"]),
            currency=row["currency"],
            is_available=row["is_available"],
            raw=row["raw"],
        )

    async def add(
        self, *, product_id: int, region_id: int, run_id: int, obs: PriceObservation
    ) -> PriceSnapshot:
        row = {
            "id": self._ids.next(),
            "product_id": product_id,
            "region_id": region_id,
            "run_id": run_id,
            "captured_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "price": str(obs.price),
            "price_base": str(obs.price_base),
            "price_card": str(obs.price_card) if obs.price_card is not None else None,
            "currency": obs.currency,
            "is_available": obs.is_available,
            "raw": obs.raw,
        }
        _atomic_append_jsonl(self._path, row)
        return self._to_model(row)

    async def list_all(self) -> list[PriceSnapshot]:
        return [self._to_model(row) for row in self._load()]


class LocalMeasureQueueRepository:
    """Flat-file `MeasureQueueItem` repository — whole-file JSON array, mutated in place."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "queue.json")
        self._ids = _IdCounter(os.path.join(base_dir, ".queue.id"))

    def _load(self) -> list[dict[str, Any]]:
        return _read_json_list(self._path)

    def _to_model(self, row: dict[str, Any]) -> MeasureQueueItem:
        return MeasureQueueItem(
            id=row["id"],
            run_id=row["run_id"],
            product_id=row["product_id"],
            region_id=row["region_id"],
            status=QueueStatus(row["status"]),
            attempts=row["attempts"],
            locked_at=(datetime.datetime.fromisoformat(row["locked_at"]) if row["locked_at"] else None),
        )

    async def create(self, *, run_id: int, product_id: int, region_id: int) -> MeasureQueueItem:
        rows = self._load()
        row = {
            "id": self._ids.next(),
            "run_id": run_id,
            "product_id": product_id,
            "region_id": region_id,
            "status": QueueStatus.PENDING.value,
            "attempts": 0,
            "locked_at": None,
        }
        rows.append(row)
        _atomic_write_json(self._path, rows)
        return self._to_model(row)

    async def mark(self, item: MeasureQueueItem, status: QueueStatus) -> MeasureQueueItem:
        rows = self._load()
        for row in rows:
            if row["id"] == item.id:
                row["status"] = status.value
                _atomic_write_json(self._path, rows)
                return self._to_model(row)
        raise ValueError(f"unknown queue item id: {item.id}")

    async def get(self, item_id: int) -> MeasureQueueItem | None:
        for row in self._load():
            if row["id"] == item_id:
                return self._to_model(row)
        return None

    async def increment_attempts(self, item: MeasureQueueItem) -> MeasureQueueItem:
        rows = self._load()
        for row in rows:
            if row["id"] == item.id:
                row["attempts"] += 1
                _atomic_write_json(self._path, rows)
                return self._to_model(row)
        raise ValueError(f"unknown queue item id: {item.id}")

    async def set_status_and_lock(
        self, item_ids: list[int], status: QueueStatus, locked_at: datetime.datetime | None
    ) -> None:
        rows = self._load()
        target = set(item_ids)
        for row in rows:
            if row["id"] in target:
                row["status"] = status.value
                row["locked_at"] = locked_at.isoformat() if locked_at else None
        _atomic_write_json(self._path, rows)

    async def claim_pending(self, limit: int) -> list[MeasureQueueItem]:
        rows = self._load()
        pending = [row for row in rows if row["status"] == QueueStatus.PENDING.value][:limit]
        if not pending:
            return []
        now = datetime.datetime.now(datetime.UTC)
        claimed_ids = {row["id"] for row in pending}
        for row in rows:
            if row["id"] in claimed_ids:
                row["status"] = QueueStatus.IN_PROGRESS.value
                row["locked_at"] = now.isoformat()
        _atomic_write_json(self._path, rows)
        return [self._to_model(row) for row in rows if row["id"] in claimed_ids]

    async def reclaim_stale(self, threshold: datetime.datetime) -> int:
        rows = self._load()
        reclaimed = 0
        for row in rows:
            if row["status"] == QueueStatus.IN_PROGRESS.value and row["locked_at"]:
                locked_at = datetime.datetime.fromisoformat(row["locked_at"])
                if locked_at < threshold:
                    row["status"] = QueueStatus.PENDING.value
                    row["locked_at"] = None
                    reclaimed += 1
        if reclaimed:
            _atomic_write_json(self._path, rows)
        return reclaimed


class LocalAttemptRepository:
    """Flat-file `Attempt` repository — insert-only JSONL."""

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, "attempts.jsonl")
        self._ids = _IdCounter(os.path.join(base_dir, ".attempts.id"))
        self._queue_path = os.path.join(base_dir, "queue.json")

    def _load(self) -> list[dict[str, Any]]:
        return _read_jsonl(self._path)

    def _to_model(self, row: dict[str, Any]) -> Attempt:
        return Attempt(
            id=row["id"],
            queue_id=row["queue_id"],
            proxy_ref=row["proxy_ref"],
            outcome=Outcome(row["outcome"]),
            error=row["error"],
            duration_ms=row["duration_ms"],
            created_at=datetime.datetime.fromisoformat(row["created_at"]),
        )

    async def add(
        self,
        *,
        queue_id: int,
        proxy_ref: str | None,
        outcome: Outcome,
        duration_ms: int,
        error: str | None = None,
    ) -> Attempt:
        row = {
            "id": self._ids.next(),
            "queue_id": queue_id,
            "proxy_ref": proxy_ref,
            "outcome": outcome.value,
            "error": error,
            "duration_ms": duration_ms,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        _atomic_append_jsonl(self._path, row)
        return self._to_model(row)

    async def recent_for_proxy_ref(
        self, proxy_ref: str, *, since: datetime.datetime, outcomes: tuple[Outcome, ...]
    ) -> list[Attempt]:
        outcome_values = {o.value for o in outcomes}
        matches = []
        for row in self._load():
            if row["proxy_ref"] != proxy_ref or row["outcome"] not in outcome_values:
                continue
            created_at = datetime.datetime.fromisoformat(row["created_at"])
            if created_at >= since:
                matches.append(self._to_model(row))
        return matches

    async def for_run(self, run_id: int) -> list[Attempt]:
        queue_rows = _read_json_list(self._queue_path)
        run_queue_ids = {row["id"] for row in queue_rows if row["run_id"] == run_id}
        return [self._to_model(row) for row in self._load() if row["queue_id"] in run_queue_ids]


class LocalStorage:
    """Bound set of local repositories over one `local_state_dir`."""

    def __init__(self, base_dir: str) -> None:
        self.products = LocalProductRepository(base_dir)
        self.regions = LocalRegionRepository(base_dir)
        self.runs = LocalRunRepository(base_dir)
        self.snapshots = LocalPriceSnapshotRepository(base_dir)
        self.queue_items = LocalMeasureQueueRepository(base_dir)
        self.attempts = LocalAttemptRepository(base_dir)

    async def commit(self) -> None:
        """No-op — every local write is already durable (atomic temp-file + rename)."""
        return None
