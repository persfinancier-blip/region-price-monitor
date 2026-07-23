# prompt-06 — Orchestration & schedule (APScheduler + Postgres queue + worker pool)

- **Branch:** `feat/orchestration`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 5](../docs/ROADMAP.md), [ADR-0004](../docs/adr/0004-scheduling-runtime.md), [ADR-0003](../docs/adr/0003-proxy-provider.md)

## Scope

**We do:** ship the orchestration layer per ADR-0004 — turn today's straight-line
`measure-wb` / `measure-ozon` loops into a **Scheduler + queue + worker pool** that can drive a
full run over every active `(product × region)` pair, safely across several workers.

Concretely, three roles behind interfaces, plus one shared measurement unit and two CLI entry
points:

1. **`TaskQueue`** — a `Protocol` plus a Postgres-backed implementation over the **existing
   `measure_queue` table** (no schema change). Claiming uses **`SELECT … FOR UPDATE SKIP
   LOCKED`** so N workers never grab the same pair. Methods: `enqueue(run_id, pairs)`,
   `claim(limit) -> list[QueueItem]` (sets `status=in_progress`, `locked_at=now` in the same
   transaction), `complete(item, status)`, and `reclaim_stale(older_than)` to return items
   abandoned by a crashed worker (`in_progress` with an old `locked_at`) back to `pending`.

2. **Shared measurement unit** — extract the per-pair body that is currently **duplicated**
   inside `_measure_wb` and `_measure_ozon` (`app/cli.py`) into one reusable async function
   (e.g. `app/collectors/measure.py::measure_pair(...)`). It takes a `(product, region)`, a
   `ProxyProvider`, the right collector, and the session/repos, and does exactly what the CLI
   does today: `provider.acquire`, time the try, `collector.collect` via `asyncio.to_thread`,
   `classify_outcome`, write a `price_snapshot` on `OK`, always write an `attempts` row, for
   Ozon `store.mark_stale` on `HARD_BAN`, `provider.report(lease, outcome)`, and return the
   `Outcome`. Dispatch WB vs Ozon by `product.marketplace`. **Refactor, don't re-implement** —
   after extraction, `measure-wb` / `measure-ozon` call the same unit and keep their current
   behaviour (including Ozon's interactive warm / non-interactive "needs warm — skip").

3. **Retry with backoff** — inside a worker, a `HARD_BAN` / `TIMEOUT` outcome is retried up to
   `settings.retry_limit` attempts with **exponential backoff** (pure helper, e.g.
   `app/scheduler/retry.py::backoff_delay(attempt)`), each retry re-acquiring a lease
   (`provider.report` between tries lets a real provider hand out a different proxy) and
   incrementing `measure_queue.attempts`. Each try still writes its own `attempts` row. `OK` /
   `SOFT_BAN` / `ERROR` are terminal (no retry). Give up after the limit → the pair's queue item
   is `failed`.

4. **Worker pool** — bounded concurrency via an `asyncio.Semaphore` sized by
   `settings.max_concurrency`. Workers loop: `claim` a small batch → run `measure_pair` (with
   retry) per item → `complete` each. The run ends when the queue drains.

5. **`Scheduler`** — an `AsyncIOScheduler` (APScheduler) wrapper that fires `run_once` on
   `settings.schedule_cron`. A `serve` CLI command starts this daemon and blocks.

6. **`run_once`** (`app/scheduler/runner.py`) — the run lifecycle: create a `run`, enqueue all
   active pairs, drain the queue with the worker pool, finalize `runs.stats` (counts per
   `Outcome` + `total`), set `runs.status`. Idempotency: `SKIP LOCKED` + the `pending →
   in_progress → done/failed` transitions guarantee each pair is processed once per run even
   with concurrent workers; a re-run is a **new** `run` with its own queue rows.

7. **CLI** — add `run-once` (trigger one full run across **all** active pairs, both
   marketplaces, through Scheduler+Queue+pool; `RunMode.MANUAL`) and `serve` (start the cron
   daemon). `run-once` is **non-interactive**: Ozon pairs whose cookies are missing/stale are
   skipped with a "needs warm" note and **no fake attempt** (reuse the existing rule); warming
   stays a separate `warm-ozon` step.

**We do NOT:**
- metrics / Prometheus, structured-log fan-out, success-rate alerts, proxy **health / cooldown**
  policy, or anti-bot tuning — that is Фаза 6 ([ROADMAP](../docs/ROADMAP.md)). Retry/backoff and
  ban handling live **here**; health scoring and observability live **there**;
- any **external broker** (Redis / Arq / Celery) — Postgres queue only (ADR-0004); keep the
  `TaskQueue` seam clean so a broker can replace it later without touching collectors;
- **server-side headless cookie warming** and multi-container deployment (Фаза 7 /
  [ADR-0006](../docs/adr/0006-panel-and-delivery.md)); the worker pool is in-process `asyncio`
  this phase;
- panel / API (Фаза 8);
- **no schema change** — reuse `runs`, `measure_queue` (`status`, `attempts`, `locked_at` are
  already there), `price_snapshots`, `attempts` as-is; **no new `Outcome`/`QueueStatus` values**;
- do not change WB/Ozon collectors, the proxy or cookie abstractions, or the parsers — this
  slice is orchestration over what is already on `main`.
Reuse the models, repos, collectors, proxy and cookie code already on `main` — do not re-model
anything.

## Body (concrete files/steps)

1. **Deps** (`pyproject.toml`): `apscheduler>=3.10` is **already** a dependency and already in
   the mypy override — no dependency change expected. Do not add a broker.

2. **Config** (`app/config.py`): `schedule_cron`, `max_concurrency`, `retry_limit` already
   exist. Add only what the queue/backoff need as **config knobs**:
   `queue_claim_batch: int = 10` (claim size per worker loop), `retry_backoff_base_s: float =
   2.0`, `retry_backoff_max_s: float = 60.0`, and `queue_lock_ttl_s: int = 600` (a
   `reclaim_stale` threshold). Mirror the shapes (not values) into `.env.example`.

3. **Task queue** (`app/queue/base.py` + `app/queue/postgres.py`):
   - `base.py`: a frozen `QueueItem` DTO (`id`, `run_id`, `product_id`, `region_id`,
     `attempts`) and a `TaskQueue` `Protocol` with `enqueue`, `claim`, `complete`,
     `reclaim_stale` (mirror the sketch in [ARCHITECTURE.md](../docs/ARCHITECTURE.md) §Ключевые
     интерфейсы; `complete` takes a terminal `QueueStatus`).
   - `postgres.py`: `PgTaskQueue(session)`.
     - `claim(limit)`: `select(MeasureQueueItem).where(status == PENDING).order_by(id)
       .limit(limit).with_for_update(skip_locked=True)`; for the returned rows set
       `status=IN_PROGRESS`, `locked_at=func.now()`, flush, return DTOs. The `SELECT` and the
       status update must be in the **same transaction** so the lock covers the update.
     - `enqueue(run_id, pairs)`: bulk-insert `pending` rows (reuse / extend
       `MeasureQueueRepository`).
     - `complete(item, status)`: set the terminal `status` (`DONE`/`FAILED`).
     - `reclaim_stale(older_than)`: `IN_PROGRESS` rows with `locked_at < now()-ttl` → back to
       `PENDING`.
     - Add a `make_task_queue(session)` factory (only `postgres` this phase).

4. **Shared measurement unit** (`app/collectors/measure.py`): pull the per-pair logic out of
   `app/cli.py` (`_measure_wb` / `_measure_ozon`) into
   `async def measure_pair(*, session, run_id, product, region, provider, wb_collector,
   ozon_collector, store, settings, interactive) -> Outcome`. It reproduces today's behaviour
   exactly (acquire lease → time → `collect` via `to_thread` → `classify_outcome` → snapshot on
   `OK` → attempt row always → Ozon `mark_stale` on `HARD_BAN` → `provider.report`) and returns
   the `Outcome`. WB vs Ozon chosen by `product.marketplace`. For Ozon it keeps the
   warm/skip contract (`OzonCookiesUnavailable` / stale-in-non-interactive → return a sentinel
   "skipped, no attempt" so the caller marks the queue item without a fake `attempts` row). The
   queue-item status transition is done by the **worker/queue**, not inside `measure_pair`.

5. **Retry** (`app/scheduler/retry.py`, pure): `backoff_delay(attempt, base, cap) -> float`
   (exponential, capped) and `is_retriable(outcome) -> bool` (`HARD_BAN`, `TIMEOUT`). Unit-test
   these directly (no sleeping in tests — inject/patch the sleep).

6. **Runner** (`app/scheduler/runner.py`):
   - `async def run_once(session_factory, settings, *, mode=RunMode.MANUAL, interactive=False)
     -> RunSummary`: open a session, create the `run`, gather active pairs (all active products
     × their applicable active regions — WB: all active regions; Ozon: active regions with an
     `ozon` geo entry, matching current CLI behaviour), `enqueue`, then run the worker pool
     (`max_concurrency` semaphore; each worker loops `claim(queue_claim_batch)` → per item
     `measure_pair` with retry → `complete`) until the queue is empty, aggregate `stats`,
     `run_repo.finish`. Commit boundaries: each pair's writes commit independently so one
     failure never rolls back the run (mirror today's "one pair's failure never aborts the run").
   - `Scheduler` class: wraps `AsyncIOScheduler`, adds a cron job from `settings.schedule_cron`
     calling `run_once(..., mode=RunMode.SCHEDULED)`; `start()` / `shutdown()`.

7. **CLI** (`app/cli.py`): add `run-once` → `run_once(..., mode=MANUAL, interactive=stdin.isatty())`
   and `serve` → build `Scheduler`, `start()`, block until Ctrl-C, `shutdown()`. Refactor
   `measure-wb` / `measure-ozon` to call the shared `measure_pair` (behaviour unchanged, tests
   stay green). Print a compact per-run summary as today (`run {id}: ok=… hard_ban=… …`).

8. **Tests** (no live network / no browser; DB tests skip cleanly without Postgres, following
   the Фаза 1/3 pattern with `TEST_DATABASE_URL`):
   - `tests/test_queue.py` (DB): `enqueue` N pending rows; **two concurrent `claim()` calls in
     separate transactions/sessions return disjoint item sets** (proves `SKIP LOCKED`);
     `claim` flips `status`/`locked_at`; `complete` sets the terminal status; `reclaim_stale`
     returns an old `in_progress` row to `pending`. Skip cleanly without a DB.
   - `tests/test_retry.py` (pure): `backoff_delay` is monotonic non-decreasing and capped at
     `retry_backoff_max_s`; `is_retriable` true for `HARD_BAN`/`TIMEOUT`, false for
     `OK`/`SOFT_BAN`/`ERROR`.
   - `tests/test_runner.py`: `run_once` over **stubbed collectors** (monkeypatch `collect` to
     return a fixed `PriceObservation` / raise a ban — no network) with a fake or in-memory
     `TaskQueue`/`ProxyProvider`, asserting: a `price_snapshot` per `OK`, an `attempts` row per
     try, retries bounded by `retry_limit`, and `runs.stats` equal to the per-outcome counts.
     Keep it DB-optional (stub the repos or gate on `TEST_DATABASE_URL`).
   - Keep every earlier phase's test green; do not skip the new SKIP-LOCKED test in CI when a DB
     is present.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the design is
  [ADR-0004](../docs/adr/0004-scheduling-runtime.md) and the `TaskQueue` sketch in
  [ARCHITECTURE.md](../docs/ARCHITECTURE.md); models, repos, collectors, proxy, cookies and CLI
  are on `main`. Build on them, don't rescan the repo.
- **`FOR UPDATE SKIP LOCKED` is mandatory** for claiming — it is the whole point of the
  Postgres queue (ADR-0004). Do not fall back to a plain `SELECT`/`UPDATE` claim.
- **Postgres queue only** — no Redis/broker; keep the `TaskQueue` seam so a broker is a drop-in
  later without touching collectors.
- Idempotency: a pair is processed once per run under concurrency; a crashed worker's item is
  recovered via `reclaim_stale`, not double-charged.
- Money stays `Decimal`; never float. No new `Outcome` / `QueueStatus` members; no schema
  change / no migration.
- Secrets never touch the repo, logs, or `attempts.proxy_ref` (masked label only) — unchanged
  from earlier phases.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green. `test_queue.py`, `test_retry.py`
  and `test_runner.py` run and pass; DB-backed tests skip cleanly **without** a DB and run
  **with** one (`TEST_DATABASE_URL`); earlier phases' tests stay green.
- `PgTaskQueue.claim` uses `FOR UPDATE SKIP LOCKED`; the concurrent-claim test proves two
  workers get disjoint items; `reclaim_stale` returns an abandoned `in_progress` item to
  `pending`.
- `run-once` drives one full run across **all** active pairs (WB + Ozon) through
  Scheduler-built queue + worker pool: a `measure_queue` row and an `attempts` row per try, a
  `price_snapshot` per `OK`, retries with backoff bounded by `retry_limit`, and `runs.stats`
  aggregating outcomes; one pair's failure never aborts the run; non-interactive Ozon
  warm-needed pairs are skipped without a fake attempt.
- `serve` starts an APScheduler daemon that fires `run_once(mode=SCHEDULED)` on
  `schedule_cron`.
- The per-pair measurement logic exists in **one** place (`measure_pair`); `measure-wb` /
  `measure-ozon` call it and behave as before.
- Manual/local check (not part of the CI gate): with a local Postgres and demo refs,
  `run-once` completes a run and, started twice concurrently in two shells, the two processes
  share the same queue without processing any pair twice.
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` Фаза 5 item checked off; the "scale
  (SKU × regions × frequency)" open question noted as satisfied-for-MVP by the Postgres-queue
  choice (broker deferred behind `TaskQueue`).
- Merged into `main` via PR with the DoD gate green.
