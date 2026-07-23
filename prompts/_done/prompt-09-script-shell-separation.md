# prompt-09 — Script/shell separation (ADR-0008), pre-Фаза 8

- **Branch:** `refactor/script-shell-separation`
- **Commit type:** `refactor:`
- **Docs:** [ADR-0008](../docs/adr/0008-script-shell-separation.md),
  [SPEC-panel.md](../docs/SPEC-panel.md) §Редактор скриптов, [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md),
  [ROADMAP.md](../docs/ROADMAP.md)

## Scope

Implement the **structural** part of [ADR-0008](../docs/adr/0008-script-shell-separation.md):
split executor logic into **standalone, interrelated scripts** that run **both** on their own and
under a thin **shell** (the shell = I/O + management only, no business logic). This is the
prerequisite the ADR names for Фаза 8 (the panel's "script editor" becomes a pipeline builder over
these scripts).

**This is an additive, behaviour-preserving refactor — wrap, don't rewrite.** The current modules
(`app/collectors/*`, `app/proxy/*`, `app/cookies/*`, `app/scheduler/*`, `app/queue/*`,
`app/obs/*`, `repositories`, `models`, `config`, `db`) are already well-factored and **stay as the
implementation**. This slice introduces a **script layer** (`app/scripts/`) that wraps them behind
clear, standalone-runnable entrypoints, plus an **orchestrator** that composes them, and turns
`app/cli.py` into a thin delegator. **No behaviour, flags, schema, or output changes** — the whole
earlier test suite stays green as the safety net.

**We do:**

1. **`app/scripts/` package** — each script is (a) importable via a typed `run(...)` function and
   (b) standalone-runnable via `python -m app.scripts.<name>` with its own `main(argv)`/argparse.
   Each reads its inputs (from `parameters`/`control-panel`/args/stdin) and writes its outputs (DB
   and/or stdout), so it works headless **and** under the shell:
   - **`parameters`** (`app/scripts/parameters.py`) — resolves connection/runtime parameters:
     wraps `app.config.Settings` + the session factory (`app.db.get_session`) + endpoints/paths
     (WB/Ozon URLs, `COOKIE_STORE_DIR`). `run()` returns a typed `Parameters` object other scripts
     consume; standalone prints the resolved parameters with **secrets/creds masked**.
   - **`control_panel`** (`app/scripts/control_panel.py`) — cities + their settings: wraps
     `RegionRepository` (active regions/geo), the proxy map (`StaticProxyProvider` inputs) and the
     schedule (`schedule_cron`). `run()` yields the active `(product × region)` work set and
     per-city settings; standalone prints active cities + settings (proxy refs masked).
   - **`health`** (`app/scripts/health.py`) — polls proxy health (`ProxyHealthService`) and cookie
     freshness (`app.cookies` staleness); on failure can trigger cookie warming
     (`warm_if_stale`) and reports proxy issues. `run()` returns a health verdict the orchestrator
     consumes; standalone prints a report and sets a non-zero exit code on unhealthy; `--fix`
     performs warming.
   - **`wb`** (`app/scripts/wb.py`) and **`ozon`** (`app/scripts/ozon.py`) — measure a
     `(product, region)` (or a batch) by wrapping `measure_pair` + the existing collectors/pacing/
     fingerprint. `run()` is importable; standalone: `python -m app.scripts.wb --sku … --region …`
     measures and writes a snapshot/attempt exactly as today.
   - **`orchestrator`** (`app/scripts/orchestrator.py`) — composes the pipeline: `parameters →
     control_panel (gather pairs) → health (verify/warm) → wb/ozon (measure via the worker pool) →
     obs (metrics + success-rate alert)`. It **reproduces `run_once` exactly** (same run lifecycle,
     queue, worker pool, retry/backoff, stats, alert) — reuse `app/scheduler/runner.py`
     internally; do not re-implement the pool. Standalone: `python -m app.scripts.orchestrator` =
     one full run. `run()` is importable and is what `Scheduler` calls on the cron tick.

2. **A minimal pipeline seam** — the orchestrator runs a **declared step sequence** (each step:
   name + the script it runs + `needs=[…]` deps), executed in dependency order. Keep it an
   **in-code structure** for now (a small `Step`/`Pipeline` dataclass in
   `app/scripts/orchestrator.py`), designed so a YAML/JSON loader (Фаза 8, ADR-0008 open question)
   can replace the hard-coded pipeline later without touching the scripts. This foreshadows the
   panel's Actions-like editor; do **not** build a YAML parser or UI here.

3. **Thin shell** — rewrite `app/cli.py` so every subcommand **delegates** to a script's
   `run()`/`main()` and does only argument parsing + output formatting. Command names, flags,
   stdout, and exit codes stay **identical** (`healthcheck`, `import-products`, `import-regions`,
   `measure-wb`, `measure-ozon`, `warm-ozon`, `run-once`, `serve`, `metrics`). `serve` builds the
   `Scheduler` whose job calls `orchestrator.run()`. No business logic remains in `cli.py`.

4. **Docs** — `docs/ARCHITECTURE.md`: add a short "Скрипты и оболочка" section describing the
   `app/scripts/` layer and the pipeline seam. `docs/ROADMAP.md`: record this slice as
   **«Рефактор — разделение скриптов и оболочки (ADR-0008), перед Фазой 8»**. Move ADR-0008 status
   to **«принято, реализуется — структурная часть в prompt-09»** (pipeline format + panel editor
   remain Фаза 8). `docs/DEVLOG.md` + `BACKLOG.md` updated.

**We do NOT:**
- **no behaviour / flag / output / schema change** — this is a structural refactor; every existing
  test must pass unchanged. If a test needs touching to follow a moved symbol, keep its assertions
  identical;
- **do not re-implement** collectors, proxy/health, cookies, the queue, the worker pool, retry, or
  observability — the scripts **wrap** those modules; `orchestrator` reuses `run_once`'s pool,
  it does not fork it;
- **no YAML/JSON pipeline format, no panel/FastAPI, no UI** — those are Фаза 8; here the pipeline
  is an in-code structure behind a clean seam;
- no new dependencies; no `.github/workflows/**` edits; no Docker/compose command-name changes
  (`serve`, `run-once`, etc. keep working so `docker-compose.prod.yml`/`Makefile` are unaffected);
- no new `Outcome`/`QueueStatus`/`RunStatus`; money stays `Decimal`; secrets stay masked.

## Body (concrete files/steps)

1. **`app/scripts/__init__.py`** + the six modules above. Each: a typed `run(...)` (in-process API
   the orchestrator/tests use) and a `main(argv: list[str] | None = None) -> int` with argparse,
   guarded by `if __name__ == "__main__": raise SystemExit(main())`, so `python -m app.scripts.<name>`
   works standalone.

2. **`parameters.py`** — `@dataclass(frozen=True) Parameters` (settings snapshot + session factory
   handle + resolved endpoints/paths). `run() -> Parameters`. Standalone prints masked params.

3. **`control_panel.py`** — `run()` → active products/regions work set + per-city settings (proxy
   ref masked, schedule). Reuse `ProductRepository`/`RegionRepository`; mirror
   `runner._active_pairs` semantics (WB: all active regions; Ozon: regions with an `ozon` geo).

4. **`health.py`** — `run(fix: bool=False) -> HealthReport` over `ProxyHealthService` +
   cookie staleness (`app.cookies.base.is_stale`), triggering `warm_if_stale` when `fix`.
   Standalone `--fix`, exit non-zero if unhealthy and not fixed.

5. **`wb.py` / `ozon.py`** — `run(...)` wrapping `measure_pair` for a product/region (or batch),
   preserving the current `measure-wb` / `measure-ozon` behaviour (interactive warm / non-interactive
   "needs warm — skip"). Standalone args mirror today's `--region` (repeatable) / `--sku`.

6. **`orchestrator.py`** — `Step`/`Pipeline` dataclasses + `run(mode=RunMode.MANUAL, interactive=False)
   -> RunSummary` that drives the declared pipeline and internally calls `run_once(...)` (the
   existing pool/queue). `Scheduler` (moved or re-exported) fires `orchestrator.run(mode=SCHEDULED)`.
   Keep `app/scheduler/runner.py` as the reused implementation; the orchestrator is the composition
   layer over it.

7. **`app/cli.py`** — each handler becomes a 1–3 line delegation to `app.scripts.<x>.run()`/`main()`
   with the same argparse surface and prints as today. `serve` → `Scheduler` over
   `orchestrator.run`.

8. **Tests** (extend, don't weaken):
   - `tests/test_scripts_*.py` — each script's `run()` unit-tested with stubbed DB/collectors (no
     network); each `main(["--help"])`/basic argv wiring smoke-tested; `health.run()` returns
     unhealthy on a stale/banned stub and triggers warm on `--fix` (warmer faked).
   - `tests/test_orchestrator.py` — the `Pipeline` runs steps in dependency order; `orchestrator.run`
     over stubbed collectors yields the **same** `RunSummary`/stats as `run_once` (reuse the
     Фаза 5/6 stubs). The artificial-ban + alert assertions from Фаза 6 still hold through the
     orchestrator path.
   - **All earlier tests stay green unchanged** (CLI delegation must not alter behaviour). If a CLI
     test imports a helper that moved, update the import only — never the assertion.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the modules to wrap are already on `main`
  (`app/collectors/*`, `app/proxy/*`, `app/cookies/*`, `app/scheduler/*`, `app/queue/*`,
  `app/obs/*`, `repositories`, `config`, `db`, `enums`). Wrap them; do not rescan or redesign.
- **Wrap, don't rewrite. Behaviour, flags, stdout, exit codes: identical.** The existing suite is
  the contract — keep it green without changing assertions.
- **Each script runs standalone (`python -m app.scripts.<name>`) AND under the shell/orchestrator.**
  The shell is convenience I/O only; no script may require the shell to run.
- `orchestrator.run` **reuses** `run_once`'s queue + worker pool + retry — no second pool.
- No new deps, no schema change, no new enum members; `.github/workflows/**` untouched; Docker/
  compose/Makefile command names unchanged.
- Money stays `Decimal`; secrets/proxy creds masked in every script's output.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG/ROADMAP/ARCHITECTURE) in
  Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green; **all pre-existing tests pass
  unchanged** (behaviour preserved); new `test_scripts_*` / `test_orchestrator` pass; DB-backed
  tests skip cleanly without Postgres and run with it.
- `app/scripts/` exists with `parameters`, `control_panel`, `health`, `wb`, `ozon`, `orchestrator`;
  **each is runnable standalone** via `python -m app.scripts.<name>` and importable via `run()`.
- `orchestrator.run()` reproduces `run-once` exactly (same run lifecycle, stats, alert) by reusing
  the existing queue/pool; the declared `Pipeline` executes steps in dependency order.
- `app/cli.py` is a **thin shell**: every command delegates to a script and only parses args /
  formats output; `serve` schedules `orchestrator.run`. All command names/flags/output unchanged —
  `docker-compose.prod.yml` and the `Makefile` keep working without edits.
- `docs/ARCHITECTURE.md` has the "Скрипты и оболочка" section; `docs/ROADMAP.md` records this
  pre-Фаза 8 refactor; ADR-0008 status updated to "реализуется (структурная часть)"; DEVLOG entry;
  BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
