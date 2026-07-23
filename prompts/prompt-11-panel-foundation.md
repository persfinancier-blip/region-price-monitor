# prompt-11 — Panel foundation + Dashboard (Фаза 8.1)

- **Branch:** `feat/panel-foundation`
- **Commit type:** `feat:`
- **Docs:** [docs/SPEC-panel.md](../docs/SPEC-panel.md) §2–3, [ADR-0006](../docs/adr/0006-panel-and-delivery.md),
  [ADR-0008](../docs/adr/0008-script-shell-separation.md), [ROADMAP → Фаза 8](../docs/ROADMAP.md)

## Scope

Start Фаза 8 (the local web panel, [SPEC-panel.md](../docs/SPEC-panel.md)) with its **foundation**:
a FastAPI app, the Vector-style tab shell, and a **read-only Dashboard** wired to the data already
in Postgres, plus a **"Run now"** action. The heavier interactive tabs (Cookies, Connection params
+ mapping, Script editor, per-city inheritance/override settings) are **later slices** — several of
them are blocked on owner open questions (Vector brand book, secret encryption, final price-field
list; SPEC §9). This slice ships only what is unblocked and gives a working panel to open in a
browser.

**Architecture rule (ADR-0008):** the panel is **another shell over `app/scripts/*`** — exactly
like `app/cli.py`. It calls script `run()` functions and read-only repositories for display; it
contains **no business logic** (no collectors, no proxy/cookie logic, no measurement). "Run now"
delegates to `app.scripts.orchestrator.run`; metrics come from `app.obs.metrics` /
`app.scripts.report`; the work set comes from `app.scripts.control_panel.run`.

**We do:**

1. **FastAPI app** (`app/panel/`) served by uvicorn, **server-rendered** with Jinja2 templates and
   minimal vanilla JS / HTMX — **no Node build step** (fits the zip-installer delivery, ADR-0006).
   A `panel` entrypoint: `region-price-monitor panel` (delegates to `app/scripts/panel.py`, which
   runs uvicorn) and standalone `python -m app.scripts.panel` — consistent with the script/shell
   split.

2. **Tab shell** (SPEC §2) — top horizontal tabs: **Панель управления**, **Куки**, **Параметры
   подключения**, **Редактор скриптов**, **Логи/история**. Only **Панель управления** (Dashboard)
   is implemented; the other four render a clean "в разработке" placeholder (so navigation exists).
   Visual layer: a neutral **Vector-OS-inspired placeholder theme** (dark, tokens in one CSS file)
   — the real Vector brand book is an open question (SPEC §9.1); keep colors/logo swappable via CSS
   variables + a single `assets/` reference.

3. **Dashboard (read-only, SPEC §3)** driven by existing data:
   - **Project health:** running/idle, last run time, last-run outcome breakdown + success rate —
     from the most recent `run` and `compute_run_metrics`.
   - **Recent runs** table (last N): id, mode, started/finished, status, per-outcome stats.
   - **Latest prices**: most recent `price_snapshot` per `(product, region)` — price, price_base,
     price_card, availability, captured_at.
   - **Active cities / work set** summary from `control_panel.run()` (proxy refs masked).
   - **"Запустить сейчас"** button → triggers `orchestrator.run` as a **background task** (returns
     immediately with the new run id / a "started" state); the dashboard reflects the new run on
     refresh. (Selective run by marketplace/city is a later slice.)

4. **Read-only query helpers** — add small read methods for the dashboard (no schema change):
   e.g. `RunRepository.list_recent(limit)` and a latest-snapshot-per-pair query (in a
   `app/panel/queries.py` or extended repo). Reads only; never mutate.

5. **Docs** — `docs/SPEC-panel.md`/`ROADMAP.md`: record the Фаза 8 slice plan (8.1 foundation+
   dashboard = this; 8.2 cities settings; 8.3 cookies; 8.4 connection+mapping; 8.5 script editor)
   and which later slices are blocked on SPEC §9 open questions. Update `docs/TZ.md` §«Не делаем» —
   the "не строим UI/дашборд" line is superseded (UI is in scope, ADR-0006/SPEC-panel), resolving
   part of SPEC §9.7. `docs/ARCHITECTURE.md`: note the panel is a shell over `app/scripts/`.
   `docs/DEVLOG.md` + `BACKLOG.md` updated.

**We do NOT:**
- **no Cookies management, no Connection-params/mapping, no Script-editor, no per-city inheritance
  editing** — those are Фаза 8.2–8.5; the Dashboard here is **read-only** except "Run now";
- **no auth / password / roles** (SPEC §9.6) — local-only for now; bind to `127.0.0.1`. Server auth
  is a later slice;
- **no secret encryption** work (SPEC §9.3) — this slice reads/writes no secrets through the UI;
- **no editing of settings/cities/cookies** through the panel; no writes to proxy maps or cookies;
- **no SPA / React / Node toolchain**; no new marketplaces; no schema change / migration; no new
  `Outcome`/`QueueStatus`/`RunStatus`; money stays `Decimal`; secrets/proxy creds masked in the UI;
- do not change collectors, proxy/cookies/queue/scheduler/obs logic, or the CLI command surface —
  the panel is additive.

## Body (concrete files/steps)

1. **Deps** (`pyproject.toml`): add `fastapi`, `uvicorn[standard]`, `jinja2` to runtime deps; add
   `fastapi`/`uvicorn`/`starlette` to the mypy `ignore_missing_imports` override if needed; add
   `httpx` to the **dev** extra (FastAPI `TestClient`).

2. **`app/panel/__init__.py`** exposing `create_app() -> FastAPI` (app factory). Mount static
   assets; configure Jinja2 templates dir.

3. **`app/panel/app.py`** — routes:
   - `GET /` → Dashboard (renders health + recent runs + latest prices + cities).
   - `GET /health` → tiny JSON liveness (app up).
   - `POST /run` → schedule `orchestrator.run(...)` via FastAPI `BackgroundTasks` (or an asyncio
     task); return a redirect/HTMX partial showing "run started". Guard against overlapping runs
     with a simple in-process flag.
   - `GET /tab/{name}` (or per-tab routes) → the four placeholder tabs.
   Data reads go through `app/panel/queries.py` (repos) + `app.obs.metrics.compute_run_metrics` +
   `app.scripts.control_panel.run`. No business logic in routes.

4. **`app/panel/queries.py`** — read-only async helpers: `recent_runs(session, limit)`,
   `latest_snapshots(session)` (latest per product×region), plus a helper to load a run's metrics.
   Reuse `RunRepository`/models; add `RunRepository.list_recent` if cleaner. Reads only.

5. **`app/panel/templates/`** — `base.html` (tab shell + theme), `dashboard.html`, `placeholder.html`.
   **`app/panel/static/`** — one `panel.css` (Vector-OS placeholder tokens via CSS variables) and a
   tiny `panel.js`/HTMX include for the "Run now" button and refresh. Keep assets self-contained
   (vendor HTMX locally or omit and use a plain form POST — no external CDN at runtime).

6. **`app/scripts/panel.py`** — `run(host="127.0.0.1", port=8000)` starts uvicorn on
   `create_app()`; `main(argv)` with `--host`/`--port`. `region-price-monitor panel` in `cli.py`
   delegates here (one line, keeps the thin-shell rule).

7. **`cli.py`** — add a `panel` subcommand (`--host`, `--port`) delegating to `app.scripts.panel`.
   No other command changes.

8. **Compose (optional, minimal)** — add a commented/optional `panel` service to
   `docker-compose.prod.yml` (command `panel --host 0.0.0.0`, port mapping) **or** just document
   running it; do not disturb the existing `app`/`postgres` services or the `serve` default.

9. **Tests** (FastAPI `TestClient`, no live network/browser; DB tests skip cleanly without
   Postgres):
   - `tests/test_panel_dashboard.py` — `GET /` returns 200 and renders health/recent-runs/latest-
     prices sections from **stubbed** queries/metrics (monkeypatch `queries`/`compute_run_metrics`/
     `control_panel.run`); secrets/proxy creds do not appear in the HTML.
   - `tests/test_panel_run.py` — `POST /run` invokes `orchestrator.run` exactly once (monkeypatched,
     not really executed) and returns the "started" response; overlapping-run guard works.
   - `tests/test_panel_placeholders.py` — the four non-dashboard tabs return 200 with the
     placeholder.
   - `tests/test_scripts_panel.py` — `panel.main(["--help"])` / arg parsing; `run()` builds the app
     without binding a socket (call `create_app()` directly, assert routes exist).
   - All earlier tests stay green.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the panel wraps `app/scripts/*`, `app/obs/metrics`,
  `RunRepository`/models, `app/db`. Don't rescan or touch the collection engine.
- **Panel = shell over scripts (ADR-0008):** no business logic in `app/panel/`; actions delegate to
  `app.scripts.*`, reads to repos/`app.obs`. No collectors/proxy/cookie/measurement code here.
- **Read-only + Run-now only.** No writes to settings/cities/cookies/proxy maps; no secret handling.
- **Local-only, no auth**, bind `127.0.0.1` by default; **no external runtime CDN** (vendor or avoid).
- **Server-rendered, no Node build.** Jinja2 + minimal JS/HTMX only.
- No schema change / migration; no new enum members; secrets/proxy creds **masked** everywhere in
  the UI; money `Decimal`.
- Do not change the existing CLI command surface (only add `panel`); Docker `serve`/compose keep
  working.
- Code/comments/commits in English; owner-facing docs (SPEC-panel/TZ/ROADMAP/ARCHITECTURE/DEVLOG/
  BACKLOG) in Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green; the new panel tests pass; DB-backed
  tests skip cleanly without Postgres; every earlier phase's test stays green.
- `region-price-monitor panel` (and `python -m app.scripts.panel`) starts a local FastAPI server on
  `127.0.0.1:8000`; opening `/` shows the **Dashboard**: project health + last-run success rate,
  recent runs, latest prices per product×region, active cities (proxy refs masked).
- **"Запустить сейчас"** triggers `orchestrator.run` in the background (same pipeline as `run-once`)
  and the dashboard reflects the new run after refresh; overlapping runs are guarded.
- The other four tabs render a placeholder; the tab shell uses a Vector-OS-inspired theme with
  swappable CSS-variable tokens (real brand book pending, SPEC §9.1).
- The panel contains **no business logic** — it calls `app.scripts.*` / `app.obs.metrics` /
  read-only repos only (a grep for `measure_pair`/`WbCollector`/`OzonCollector`/`make_proxy_provider`
  in `app/panel/` returns nothing).
- No secret or proxy credential is rendered in any page.
- `docs/SPEC-panel.md`/`ROADMAP.md` record the Фаза 8 slice plan and blocked-by-open-question tabs;
  `docs/TZ.md` §«Не делаем» updated (UI in scope); `docs/ARCHITECTURE.md` notes the panel-as-shell;
  DEVLOG entry added; BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
