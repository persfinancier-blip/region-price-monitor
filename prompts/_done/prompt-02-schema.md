# prompt-02 — Data model & migrations

- **Branch:** `feat/schema`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md → Модель данных](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 1](../docs/ROADMAP.md), [ADR-0001](../docs/adr/0001-stack.md)

## Scope

**We do:** define the persistent data model — SQLAlchemy 2.x ORM models for all six tables on the existing `Base` (`app/db.py`), typed enums, the first real Alembic migration (up **and** down), repositories for the two reference tables (`products`, `regions`) with idempotent upsert, and CLI import commands that load a demo dataset. This is the storage foundation later phases build on.

**We do NOT:** implement any collector, proxy, scheduler, or marketplace call. No queue claim logic (`FOR UPDATE SKIP LOCKED` lands in Фаза 5), no run orchestration, no write-paths for `runs` / `measure_queue` / `price_snapshots` / `attempts` beyond their table definitions. No panel/API.

## Body (concrete files/steps)

1. **Enums** (`app/enums.py`): `str`-backed `enum.Enum` types — `Marketplace` (`wb`|`ozon`), `RunMode` (`scheduled`|`manual`), `RunStatus` (`running`|`done`|`failed`), `QueueStatus` (`pending`|`in_progress`|`done`|`failed`), `Outcome` (`ok`|`soft_ban`|`hard_ban`|`timeout`|`error`). Persist as native PG `ENUM` (created by the migration).
2. **Models** (`app/models.py`) on `Base` from `app.db`, SQLAlchemy 2.0 typed (`Mapped` / `mapped_column`), matching [ARCHITECTURE.md → Модель данных](../docs/ARCHITECTURE.md):
   - `products` — `id`, `marketplace` (enum), `sku`, `url`, `name`, `is_active` (default true), `created_at` (tz-aware, server default now). Unique `(marketplace, sku)`.
   - `regions` — `id`, `code` (unique), `name`, `geo` (`JSONB`), `is_active`.
   - `runs` — `id`, `mode` (enum), `status` (enum), `started_at`, `finished_at` (nullable), `stats` (`JSONB`, default `{}`).
   - `measure_queue` — `id`, `run_id` FK→runs, `product_id` FK→products, `region_id` FK→regions, `status` (enum, default `pending`), `attempts` (int, default 0), `locked_at` (nullable).
   - `price_snapshots` — `id`, `product_id` FK, `region_id` FK, `run_id` FK, `captured_at` (tz-aware), `price`, `price_base`, `price_card` (numeric, nullable), `currency`, `is_available` (bool), `raw` (`JSONB`). Insert-only history.
   - `attempts` — `id`, `queue_id` FK→measure_queue, `proxy_ref` (nullable), `outcome` (enum), `error` (nullable text), `duration_ms` (int), `created_at`.
   - Indexes: `price_snapshots (product_id, region_id, captured_at DESC)`, `measure_queue (status, run_id)`.
   - Use `sqlalchemy.dialects.postgresql.JSONB` and `Numeric` for money. Keep money as `Numeric`/`Decimal`, never float.
3. **Metadata wiring:** add `from app import models  # noqa: F401` to `migrations/env.py` so `Base.metadata` is populated for autogenerate. (Alembic is already wired to `Base.metadata` in the skeleton.)
4. **First migration** (`migrations/versions/*_initial_schema.py`): create all enums, six tables, FKs and the two indexes. Autogenerate, then **review by hand** (enum creation order, `JSONB`, index direction). `alembic upgrade head` on an empty DB and `alembic downgrade base` back to empty must both succeed cleanly.
5. **Repositories** (`app/repositories.py`, async, over `AsyncSession`): `ProductRepository` and `RegionRepository` with `upsert(...)` (idempotent — `products` on `(marketplace, sku)`, `regions` on `code`, via PG `ON CONFLICT`) and `list_active()`. The other four tables get models only this phase — no repos yet.
6. **CLI import:** extend the existing `argparse` CLI (`app/cli.py`) with `import-products <file.json>` and `import-regions <file.json>` subcommands that read JSON and upsert via the repositories. Re-running the same file must not create duplicates (idempotent). Print a short `imported N / updated M` summary.
7. **Demo dataset** (`data/seed/products.json`, `data/seed/regions.json`): a handful of WB+Ozon SKUs and 2–3 regions (e.g. `msk`, `spb`) with realistic `geo` shapes (WB `dest`; Ozon city/coords/address). Small, illustrative.
8. **Tests** (`tests/test_repositories.py`): exercise upsert idempotency and `list_active` against a real Postgres. A session-scoped fixture reads `TEST_DATABASE_URL` (fallback `DATABASE_URL`), runs `alembic upgrade head` on a scratch schema, and yields a session; **if the DB is unreachable, `pytest.skip` the module** — so the DoD gate stays green in CI (no Postgres in the runner) and the tests run for real locally once Postgres is up. Keep the existing smoke test.

## Constraints

- Model = Sonnet (pinned). Minimal read scope; do not scan the whole repo — the skeleton (`app/db.py` `Base`, `app/config.py`, `app/cli.py`, `migrations/env.py`) is already on `main`.
- No Postgres service in the CI runner and `.github/workflows/**` is not dispatchable to the worker — DB-backed tests therefore **skip when no DB is reachable** (owner's decision, 2026-07-22); the schema/migration/repo path is verified locally.
- Secrets never committed; `.env` gitignored, only `.env.example` holds any new shape.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy + pytest) exits green; repo tests skip cleanly when no DB is present, smoke test passes.
- Against a local Postgres: `alembic upgrade head` creates all six tables + enums + indexes; `alembic downgrade base` reverts to an empty schema with no errors.
- `import-products` and `import-regions` load `data/seed/*.json`; a second run of each is idempotent (no duplicate rows).
- With `TEST_DATABASE_URL` set, `tests/test_repositories.py` runs (not skipped) and is green.
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` Фаза 1 item checked off.
- Merged into `main` via PR with the DoD gate green.

<!-- dispatched for Фаза 1 (schema) → worker, 2026-07-22 -->
