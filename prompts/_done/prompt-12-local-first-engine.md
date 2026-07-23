# prompt-12 — Local-first engine: run with no Postgres (revises ADR-0004)

- **Branch:** `feat/local-first-engine`
- **Commit type:** `feat:`
- **Docs:** [ADR-0004](../docs/adr/0004-scheduling-runtime.md) (revised here),
  [ADR-0008](../docs/adr/0008-script-shell-separation.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md),
  [docs/SPEC-panel.md](../docs/SPEC-panel.md) §5, [ROADMAP.md](../docs/ROADMAP.md)

## Scope

Owner decision (2026-07-23): **the absence of Postgres must not block the product — it must run
fully locally, with no database.** This slice delivers that: the engine's **internal working state
moves to local flat files**, and Postgres becomes **optional**. Record the pivot as
`docs/adr/0009-local-first-storage.md` (revises [ADR-0004](../docs/adr/0004-scheduling-runtime.md)).

**This slice = internal state local + the whole loop runs with no Postgres.** The configurable
**source/sink adapters (CSV/Excel/DB) + field mapping** and the **setup helper/wizard** are the
**next slices** (`prompt-13`, `prompt-14`) — call them out in docs, don't build them here. For now:
input comes from the existing `import-products`/`import-regions` (local JSON) into the local store,
and results (`price_snapshots`) are written to the local store.

**We do:**

1. **Storage seam.** Introduce repository **Protocols** matching today's repository method sets
   (`Product`, `Region`, `Run`, `MeasureQueue`, `Attempt`, `PriceSnapshot`) and a
   **`make_storage(settings)`** factory that returns a bound set of repositories for the selected
   backend. Two backends:
   - **`local`** (default) — flat-file implementations under `settings.local_state_dir` (JSON /
     JSONL, script-owned; e.g. `products.json`, `regions.json`, `runs.jsonl`, `attempts.jsonl`,
     `snapshots.jsonl`, `queue.json`). Atomic writes (temp-file + rename); ids are monotonic local
     counters.
   - **`postgres`** — the existing SQLAlchemy repositories, kept behind the same seam (optional,
     only when `storage_backend=postgres`).

2. **Local task queue.** Add a **local `TaskQueue`** implementation (the `Protocol` already exists,
   `app/queue/base.py`) backed by the local store / in-process — single machine, so **no
   `SKIP LOCKED`** is needed for the local backend (that concurrency guarantee is a Postgres-only
   capability; document it). `make_task_queue` picks the impl by `storage_backend`. The worker pool
   still runs in-process via `asyncio`.

3. **Wire the engine through the seam.** `run_once`/`orchestrator`, `measure_pair`, the `wb`/`ozon`/
   `control_panel`/`health`/`report` scripts, and the panel's read path build repositories via
   `make_storage(settings)` (and the queue via `make_task_queue`) instead of constructing
   SQLAlchemy repos directly. `ProxyHealthService` reads recent attempts from the **store** (local
   or pg); `compute_run_metrics` reads runs/attempts from the store. Behaviour is identical on
   either backend.

4. **No DB required to run.** With `STORAGE_BACKEND=local` (the default): `import-regions` /
   `import-products` populate the local store; `run-once` / `measure-*` measure and write
   `snapshots`/`attempts`/`runs` locally; `metrics` / `health` / `panel` read locally — **all with
   no Postgres process, no `asyncpg`, no migrations**. The Docker entrypoint runs
   `alembic upgrade head` **only** when `storage_backend=postgres`.

5. **No secret store.** Local single-user: proxy/DB credentials live in plain local config the user
   controls — drop any secret-encryption expectation for local mode (SPEC §9.3). Keep `.env`
   support; nothing new to encrypt here.

6. **Docs.** `docs/adr/0009-local-first-storage.md` recording the pivot (local-first, Postgres
   optional, flat-file internal state, source/sink each local-or-DB + mapping and a setup helper as
   **next** slices, no secret store) and marking [ADR-0004](../docs/adr/0004-scheduling-runtime.md)
   **superseded in part** (Postgres queue → optional). `docs/OPS.md`: a **"Локальный режим (без
   Postgres)"** section — zero-DB quickstart. `docs/ARCHITECTURE.md`: the storage seam + backends.
   `docs/ROADMAP.md`: record this slice and the `prompt-13` (source/sink adapters + mapping) /
   `prompt-14` (setup helper) plan. `docs/TZ.md`: note local-first / DB-optional. `DEVLOG.md` +
   `BACKLOG.md` updated.

**We do NOT:**
- **no CSV/Excel/DB source-sink adapters and no field mapping yet** — that is `prompt-13`; here the
  source is the existing local-JSON import and the sink is the local store;
- **no setup wizard** — that is `prompt-14`;
- **do not delete** the Postgres path — keep it working behind the seam (`storage_backend=postgres`);
  this is additive, not a removal;
- no panel feature tabs (8.2–8.5); no new marketplaces; no new `Outcome`/`QueueStatus`/`RunStatus`;
  money stays `Decimal`;
- do not change collector/proxy/cookie/parser logic, the CLI command surface, or observability
  behaviour — only where they read/write state, route it through the seam.

## Body (concrete files/steps)

1. **Config** (`app/config.py`, mirror into `.env.example`): `storage_backend: str = "local"`
   (`local` | `postgres`), `local_state_dir: str = "data/state"`. Keep `database_url` (used only
   when `postgres`).

2. **`app/storage/base.py`** — repository `Protocol`s for `Product/Region/Run/MeasureQueue/Attempt/
   PriceSnapshot` mirroring the current `app/repositories.py` method signatures exactly, plus a
   `Storage` bundle type and a `make_storage(settings)` factory.

3. **`app/storage/local.py`** — flat-file implementations (JSON/JSONL under `local_state_dir`),
   atomic writes, monotonic ids, the same return types (reuse `app/models` dataclasses or introduce
   plain DTOs the repos already return). Implement the query shapes the engine needs
   (`list_active`, `get_by_*`, insert-only snapshots/attempts, run create/finish, queue
   enqueue/claim/complete/reclaim, recent-attempts-for-proxy_ref, runs/attempts for metrics).

4. **`app/storage/postgres.py`** — thin adapter exposing the existing `app/repositories.py` classes
   through the new Protocols (no logic change).

5. **`app/queue/local.py`** — `LocalTaskQueue` implementing `TaskQueue` over the local store
   (`enqueue`/`claim`/`complete`/`reclaim_stale`); `make_task_queue(settings, …)` returns the
   local or pg impl by backend. Note in code+docs that cross-process `SKIP LOCKED` is pg-only.

6. **Rewire** `app/scheduler/runner.py`, `app/collectors/measure.py`, and `app/scripts/*`
   (`wb`, `ozon`, `control_panel`, `health`, `report`, `orchestrator`) and `app/panel/queries.py`
   to obtain repositories via `make_storage(settings)` / the queue via `make_task_queue` instead of
   direct SQLAlchemy repos/sessions. Keep the public function signatures; inject the storage bundle
   the way sessions/repos are injected today (default-construct from settings, override in tests).

7. **Docker entrypoint** (`docker/entrypoint.sh`): run `alembic upgrade head` only when
   `STORAGE_BACKEND=postgres`; on `local`, ensure `LOCAL_STATE_DIR` exists and skip migrations.
   `docker-compose.prod.yml`: make `postgres` optional (e.g. a compose profile) so `app` runs
   standalone in local mode; keep the pg service available for `storage_backend=postgres`.

8. **Tests** (no live network; **the local backend needs no DB and must be fully covered**):
   - `tests/test_storage_local.py` — every local repo op round-trips through files (tmp dir):
     upsert/list/get, insert-only snapshots/attempts, run lifecycle, queue enqueue/claim/complete/
     reclaim, recent-attempts-for-proxy_ref, metrics aggregation inputs. Atomic-write safety.
   - `tests/test_local_end_to_end.py` — with `storage_backend=local` and a tmp state dir, stubbed
     collectors (no network): `import` → `run_once` writes runs/attempts/snapshots locally →
     `compute_run_metrics` / `health` read them — **no Postgres**.
   - Update existing tests to run against the local backend by default; keep the Postgres-gated
     tests (`TEST_DATABASE_URL`) green when a DB is present. No assertion changes beyond backend
     wiring.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the seam wraps `app/repositories.py`,
  `app/models.py`, `app/queue/*`, `app/scheduler/runner.py`, `app/collectors/measure.py`,
  `app/scripts/*`, `app/config.py`. Don't rescan collectors/proxy/parser internals.
- **Local backend is the default and must run with zero Postgres** — no `asyncpg` connection, no
  migrations, no server. Postgres stays fully working behind the seam when selected.
- **Behaviour identical on both backends**: same outcomes, stats, stdout, exit codes; existing
  tests stay green (adapt only backend wiring, not assertions).
- Flat-file writes are **atomic** (temp + rename) and insert-only where the pg tables are
  insert-only (`snapshots`, `attempts`). Money stays `Decimal` (serialize as string, not float).
- **No secret store**; creds live in plain local config. Secrets/proxy creds still **masked** in
  logs/UI output.
- No new marketplaces; no new enum members; CLI command surface unchanged; the panel keeps working
  via the seam.
- Code/comments/commits in English; owner-facing docs (ADR/OPS/ARCHITECTURE/ROADMAP/TZ/DEVLOG/
  BACKLOG) in Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green. `test_storage_local.py` and
  `test_local_end_to_end.py` pass **without any database**; Postgres-gated tests still pass with a
  DB; all earlier tests stay green.
- With `STORAGE_BACKEND=local` (default) and **no Postgres running**: `import-regions` +
  `import-products` populate `LOCAL_STATE_DIR`; `run-once` completes a run and writes
  runs/attempts/snapshots as local files; `metrics --last`, `health`, and the `panel` dashboard all
  read that local state. No `asyncpg`/migration/DB is touched.
- `STORAGE_BACKEND=postgres` reproduces the previous behaviour end-to-end (seam parity).
- The Docker entrypoint migrates only on the pg backend; `app` runs standalone (no `postgres`
  service) in local mode via `docker-compose.prod.yml`.
- `docs/adr/0009-local-first-storage.md` records the pivot and marks ADR-0004 partly superseded;
  `docs/OPS.md` has a zero-DB "Локальный режим" quickstart; `docs/ARCHITECTURE.md` documents the
  storage seam; `docs/ROADMAP.md` records this slice + `prompt-13` (source/sink adapters + mapping)
  and `prompt-14` (setup helper); `docs/TZ.md` notes local-first/DB-optional; DEVLOG + BACKLOG
  updated.
- Merged into `main` via PR with the DoD gate green.
