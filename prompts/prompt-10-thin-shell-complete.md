# prompt-10 — Finish the thin shell: move ALL logic into scripts (ADR-0008)

- **Branch:** `refactor/thin-shell-complete`
- **Commit type:** `refactor:`
- **Docs:** [ADR-0008](../docs/adr/0008-script-shell-separation.md),
  [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §Скрипты и оболочка, [ROADMAP.md](../docs/ROADMAP.md)

## Scope

Complete the ADR-0008 split started in `prompt-09`. Today most executor logic already lives in
`app/scripts/*`, but a handful of commands still have their bodies inside `app/cli.py`
(`import-products`, `import-regions`, `warm-ozon`, `metrics`, `healthcheck`, `serve`) and the
`measure-wb`/`measure-ozon` handlers still assemble dependencies the scripts now build themselves.

The owner may not use the shell at all — so **every command must be fully runnable as a standalone
script** (`python -m app.scripts.<name> …`), and `app/cli.py` must become a **pure dispatcher**:
parse args, `configure_logging`, call a script, return its exit code. **No business logic, no repo/
provider/session/collector usage, no DB access remains in `cli.py`.**

**Behaviour-preserving refactor — wrap/move, don't rewrite.** Command names, flags, stdout, exit
codes stay identical (so `docker-compose.prod.yml`, the `Makefile`, and the entrypoint keep
working). The whole existing test suite stays green as the contract.

**We do:**

1. **Import → `control_panel`.** Move `_import_products` / `_import_regions` (JSON load + repo
   upsert + the `imported/updated` summary line) into `app/scripts/control_panel.py` as
   `import_products(path, …)` / `import_regions(path, …)` functions, plus standalone subcommands
   `python -m app.scripts.control_panel import-products <file>` / `import-regions <file>` (keep the
   existing default action — printing the work set — as e.g. `show`/no-subcommand).

2. **`warm-ozon` → `health`.** Move `_warm_ozon` (iterate regions, acquire a lease, `warm_if_stale`,
   print `region=<code>: warmed`) into `app/scripts/health.py` as `warm(region_codes, …)` with a
   standalone subcommand `python -m app.scripts.health warm [--region …]`. Keep the existing
   default health report + `--fix` behaviour.

3. **`metrics` → new `app/scripts/report.py`.** Move `_metrics` (resolve `--run`/`--last`, call
   `compute_run_metrics`, print the human summary + `to_prometheus`, emit the structured `metrics`
   log) into a new `report` script wrapping `app/obs/metrics.py`. Standalone:
   `python -m app.scripts.report --run <id> | --last`. (Name it `report` to avoid colliding with
   `app/obs/metrics.py`.)

4. **`healthcheck` → `parameters`.** Move `_run_healthcheck` (DB connectivity via
   `app.db.healthcheck`, `OK` / non-zero) into `app/scripts/parameters.py` as a `--check` action
   (default still prints the resolved, masked parameters). `python -m app.scripts.parameters --check`.

5. **`serve` → `orchestrator`.** Move `_serve` (build the APScheduler `Scheduler`, block, shutdown)
   into `app/scripts/orchestrator.py` as `serve(…)`, and point the scheduled job at
   **`orchestrator.run`** (not `run_once` directly), so a scheduled run follows the same pipeline as
   `run-once`. Standalone: `python -m app.scripts.orchestrator serve` (keep bare
   `python -m app.scripts.orchestrator` = one pipeline pass). Reuse the existing
   `app/scheduler/runner.py::Scheduler` (extend it to accept the pipeline callable, or wrap it) —
   do not fork the scheduler.

6. **Simplify `measure-wb` / `measure-ozon` handlers.** The `wb`/`ozon` scripts already
   default-construct settings/provider/cookie store/collectors when not injected — drop the
   redundant wiring from `cli.py` so those handlers just call `wb.run(region, sku)` /
   `ozon.run(region, sku)`.

7. **`cli.py` becomes a pure dispatcher.** After this, `cli.py` imports only argparse/asyncio,
   `configure_logging`, and the `app.scripts.*` modules. Each subcommand handler is a one-liner
   delegating to a script's `run()`/`main()`. Keep the exact same subparsers, flags, help text,
   stdout, and exit codes. `main` still calls `configure_logging(get_settings())` once.

8. **Docs.** `docs/ARCHITECTURE.md` §Скрипты и оболочка: add the full **command ↔ script** map and
   the standalone `python -m app.scripts.<name>` invocation for every command; state explicitly
   that the shell is an optional convenience and each script runs headless on its own. Move ADR-0008
   status to **«реализовано (структурная часть) — вся исполнительская логика в `app/scripts/`,
   `cli.py` — чистый диспетчер»** (pipeline YAML format + panel editor still Фаза 8). Update
   `docs/DEVLOG.md` and `BACKLOG.md`.

**We do NOT:**
- **no behaviour / flag / stdout / exit-code / schema change** — pure structural move; every
  existing test passes unchanged (update only imports if a symbol moved, never assertions);
- **do not rewrite** the wrapped implementations (collectors, proxy/health, cookies, queue, pool,
  retry, obs, repositories) — scripts keep wrapping them;
- **no new command names**; `docker-compose.prod.yml` / `Makefile` / entrypoint keep calling
  `region-price-monitor <same-cmd>` unchanged;
- no YAML/JSON pipeline format, no panel/FastAPI/UI (Фаза 8); no new deps; no `.github/workflows/**`
  edits; no new `Outcome`/`QueueStatus`/`RunStatus`; money stays `Decimal`; secrets stay masked.

## Body (concrete files/steps)

1. **`app/scripts/control_panel.py`** — add `async def import_products(path, *, session_factory=get_session)`
   and `async def import_regions(path, *, session_factory=get_session)` (exact logic + output moved
   from `cli.py`). Turn `main` into a small subcommand parser: `import-products <file>`,
   `import-regions <file>`, and the current work-set print as the default/`show`.

2. **`app/scripts/health.py`** — add `async def warm(region_codes, *, session_factory=get_session,
   settings=None, cookie_store=None, provider=None, warmer=None)` reproducing `_warm_ozon` exactly
   (unknown region → stderr + exit 1; per-region `warm_if_stale`; `region=<code>: warmed`). Add a
   `warm [--region …]` subcommand to `main`; keep the default report + `--fix`.

3. **`app/scripts/report.py`** (new) — `async def run(run_id, last, *, session_factory=get_session)`
   with the `_metrics` body (the `--run`/`--last` resolution, human line, `to_prometheus`, structured
   `metrics` log). `main` mirrors the `metrics` command's mutually-exclusive `--run/--last`.

4. **`app/scripts/parameters.py`** — add `async def healthcheck() -> int` wrapping
   `app.db.healthcheck` (same `OK`/stderr/exit codes) and a `--check` flag in `main`.

5. **`app/scripts/orchestrator.py`** — add `async def serve(*, session_factory=None, settings=None)`
   that starts the scheduler firing `orchestrator.run(mode=SCHEDULED)` and blocks until interrupt,
   then `shutdown()` (move the `_serve` loop). Add a `serve` subcommand to `main`; bare invocation
   stays one pipeline pass. Adjust `app/scheduler/runner.py::Scheduler` so its cron job can call the
   pipeline (`orchestrator.run`) — e.g. accept an optional job callable, defaulting to preserve
   current behaviour — without duplicating the APScheduler wiring.

6. **`app/cli.py`** — reduce every handler to a delegation:
   `healthcheck`→`parameters` (`--check`), `import-products`/`import-regions`→`control_panel`,
   `measure-wb`→`wb.run`, `measure-ozon`→`ozon.run`, `warm-ozon`→`health.warm`,
   `run-once`→`orchestrator.run`, `serve`→`orchestrator.serve`, `metrics`→`report.run`. Remove all
   now-unused imports (repositories, providers, collectors, models, obs.metrics, get_session, …).
   Keep the subparser definitions and `configure_logging`.

7. **Tests** (extend; keep all existing green):
   - Extend `tests/test_scripts_control_panel.py` — `import_products`/`import_regions` write/upsert
     correctly (DB-gated, skip cleanly without Postgres) and the subcommand parser dispatches.
   - Extend `tests/test_scripts_health.py` — `warm(...)` warms per region and prints the expected
     line (warmer faked, no browser); unknown region → exit 1.
   - `tests/test_scripts_report.py` (new) — `report.run` prints the summary + Prometheus text and
     handles `--last`/`--run`/missing-run (compute path faked or DB-gated).
   - Extend `tests/test_scripts_parameters.py` — `--check` returns the healthcheck exit code
     (`app.db.healthcheck` monkeypatched).
   - Extend `tests/test_orchestrator.py` — `serve` wires a scheduler whose job is `orchestrator.run`
     (assert the scheduled callable, no real blocking/sleep — patch the scheduler/loop).
   - `tests/test_cli.py` (new or extended) — `cli.main([...])` for each command delegates to the
     right script (monkeypatch the script's `run`/`main`, assert it's called with the parsed args);
     proves `cli.py` holds no logic. Every pre-existing test stays green.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the moving targets are `app/cli.py` and
  `app/scripts/*` (both fully on `main`); the wrapped modules are unchanged. Don't rescan the repo.
- **Move, don't rewrite. Identical behaviour/flags/stdout/exit codes.** Existing tests are the
  contract — keep them green without editing assertions (imports may be updated).
- **Every command runs standalone** via `python -m app.scripts.<name> …`; the shell is optional.
  No script may depend on `cli.py`.
- `cli.py` after this: **no DB/repo/provider/collector/obs logic** — argparse + `configure_logging`
  + delegation only.
- `serve` and `run-once` must drive the **same** `orchestrator.run` pipeline; no second scheduler,
  no forked pool. Behaviour of a scheduled run is unchanged except that it now flows through the
  (read-only pre-steps of the) pipeline, exactly like `run-once` already does.
- No new deps / no schema change / no new enum members; `.github/workflows/**` untouched; Docker/
  compose/Makefile command names unchanged. Money `Decimal`; secrets/proxy creds masked in output.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG/ROADMAP/ARCHITECTURE, ADR) in
  Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green; **all pre-existing tests pass
  unchanged**; the new/extended script + CLI tests pass; DB-backed tests skip cleanly without
  Postgres and run with it.
- `app/cli.py` is a **pure dispatcher**: it imports only argparse/asyncio, `configure_logging`, and
  `app.scripts.*`; every subcommand is a one-line delegation; no repo/provider/collector/session/
  obs code remains. (A grep for `Repository`/`make_proxy_provider`/`get_session`/`measure_pair` in
  `cli.py` returns nothing.)
- Every command is runnable standalone and equivalent to the shell:
  `parameters --check` (healthcheck), `control_panel import-products|import-regions <file>`,
  `wb`/`ozon` (measure), `health warm` (warm-ozon), `orchestrator` (run-once) / `orchestrator serve`,
  `report --run|--last` (metrics). Same output and exit codes as the corresponding
  `region-price-monitor <cmd>`.
- `serve` schedules `orchestrator.run`; `run-once` and a scheduled run follow the same pipeline.
- `docker-compose.prod.yml`, `Makefile`, and the Docker entrypoint work unchanged (same command
  names/flags).
- `docs/ARCHITECTURE.md` has the command↔script map + standalone invocations and states the shell is
  optional; ADR-0008 status updated; `docs/DEVLOG.md` entry added; `BACKLOG.md` updated.
- Merged into `main` via PR with the DoD gate green.
