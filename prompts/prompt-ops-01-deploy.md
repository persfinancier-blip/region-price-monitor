# prompt-ops-01 — Deploy core: runnable prod image + compose + ops docs (no installer)

- **Branch:** `feat/deploy-core`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md) §Нефункциональные требования (портируемость/секреты),
  [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 7](../docs/ROADMAP.md),
  [ADR-0004](../docs/adr/0004-scheduling-runtime.md), [ADR-0006](../docs/adr/0006-panel-and-delivery.md),
  [SPEC-panel.md](../docs/SPEC-panel.md)

## Scope

This is **Фаза 7, part 1 — deploy core**: make the service **runnable and battle-testable
against real WB/Ozon + real proxies**, so the owner can launch it and validate "in the field"
before anything gets packaged. The **zip auto-installer / bootstrap** (ADR-0006) and the **final
hosting choice** are explicitly **deferred** — the owner wants to run and test first.

This slice also **records** (documentation only) the owner's forward-looking architecture rework
as `docs/adr/0008-script-shell-separation.md` — see §7. It does **not** implement that rework.

**We do:**

1. **Finalize the Dockerfile for real runs.** Keep the Playwright base (Ozon cookie warming needs
   it, ADR-0005). Add: an **entrypoint** that runs `alembic upgrade head` and then `exec`s the
   requested command (so migrations always apply before serving); a non-root runtime user;
   install the package (no dev extras); default `CMD` = `serve`. `run-once`, `serve`, `warm-ozon`,
   `metrics`, `healthcheck`, `import-products`, `import-regions` must all be invokable as the
   container command.

2. **A production compose** (`docker-compose.prod.yml`): `app` runs `serve` (the APScheduler
   daemon) with `restart: unless-stopped`, reads config from `.env` (`env_file`), and mounts a
   **named volume for the cookie store** (`COOKIE_STORE_DIR`, default `data/cookies`) so warmed
   Ozon cookies survive restarts; `postgres:16` with its own named volume and healthcheck; `app`
   `depends_on` postgres healthy. Do not expose Postgres publicly by default. The existing
   dev `docker-compose.yml` stays as-is for local `healthcheck`.

3. **Operator helpers** (`Makefile` or `scripts/*.sh`, thin wrappers only, no business logic):
   `build`, `up` / `down` (prod compose), `migrate`, `run-once`, `warm-ozon`, `metrics`, `logs`.
   These are convenience for the field test — the app entrypoints are unchanged.

4. **Ops documentation** (`docs/OPS.md`, in Russian — owner-facing) that takes an operator from a
   clone to a live measurement: fill `.env` (DB DSN, `PROXY_MAP_JSON` per region, thresholds,
   `ALERTER`/`ALERT_WEBHOOK_URL`); bring up Postgres; run migrations; `import-regions` /
   `import-products`; **warm Ozon cookies** (`warm-ozon`, note it needs a headful/manual step —
   ADR-0006 open question, do it locally for now); a **`run-once` smoke test**; start `serve`;
   read `metrics` and the structured JSON logs; where the cookie/DB volumes live; how to update
   (pull → `build` → migrations run on entrypoint). Include a short **"боевой прогон" checklist**.

5. **Env parity.** Ensure `.env.example` covers every knob the prod compose and ops docs reference
   (it already lists DB/proxy/health/pacing/observability — add anything new the compose needs,
   e.g. a `COOKIE_STORE_DIR` note for the volume). No secrets in the repo.

**We do NOT:**
- **no zip auto-installer / bootstrap / загрузочные файлы** (ADR-0006) — deferred to a later
  `prompt-ops-02`; the owner tests the raw containers first;
- **no final hosting decision** — keep everything portable containers; the "выбор хостинга" open
  question stays open (note it in DEVLOG, don't close it);
- **do not implement** the script/shell separation rework — this slice only **records ADR-0008**
  (§7); no code is restructured;
- no panel / FastAPI (Фаза 8); no CI/CD changes under `.github/workflows/**` (those are
  local-only per [github-automation](../.claude/rules/github-automation.md));
- no app-logic, schema, collector, queue, or observability changes — reuse everything on `main`.

## Body (concrete files/steps)

1. **`Dockerfile`** — keep `FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy`. Copy
   `pyproject.toml`, `app`, `migrations`, `alembic.ini`; `pip install --no-cache-dir .` (not `-e`,
   prod). Add `COPY docker/entrypoint.sh /entrypoint.sh` + `chmod +x`; create a non-root user and
   `USER` it (ensure it can write `COOKIE_STORE_DIR`); `ENTRYPOINT ["/entrypoint.sh"]`,
   `CMD ["serve"]`. The entrypoint runs `alembic upgrade head` then `exec region-price-monitor "$@"`.

2. **`docker/entrypoint.sh`** — `set -euo pipefail`; wait/allow for DB (compose `depends_on`
   healthy already covers it), `alembic upgrade head`, then `exec region-price-monitor "$@"`.

3. **`docker-compose.prod.yml`** — as in Scope §2: `postgres` (named volume, healthcheck), `app`
   (`build: .`, `env_file: .env`, `command: ["serve"]`, `restart: unless-stopped`, cookie named
   volume at `COOKIE_STORE_DIR`). Keep `DATABASE_URL` pointing at the `postgres` service host.

4. **`Makefile`** (or `scripts/ops-*.sh`) — thin targets wrapping
   `docker compose -f docker-compose.prod.yml ...` for build/up/down/migrate/run-once/warm-ozon/
   metrics/logs. No logic beyond the compose/exec calls.

5. **`docs/OPS.md`** — the runbook from Scope §4 (Russian). Cross-link ROADMAP Фаза 7 and the
   relevant ADRs. Make the **field-test checklist** explicit and copy-pasteable.

6. **`.env.example`** — top up with any new keys the compose/docs reference; keep the "never
   commit .env" note.

7. **`docs/adr/0008-script-shell-separation.md`** (record only — do NOT implement). Capture the
   owner's decision (2026-07-23): all executor logic moves into **standalone, interrelated Python
   scripts** that run both on their own and under a thin **shell** (оболочка = I/O + management
   only, no business logic); the panel's **script-editor** section gets a **GitHub-Actions-like
   pipeline** (step sequences/dependencies) over these scripts. List the planned scripts:
   **control-panel** (cities + their settings: proxies, cookies, schedules), **parameters**
   (connection addresses — what to write where, what to read into the local DB), **health**
   (polls cookies/proxies; on failure triggers cookie-warm or proxy-update), **wb** (and
   per-marketplace peers — pull from control-panel/parameters, parse), and an **orchestrator**
   (runs script sequences, owns order/startup; propose a name, e.g. `runner`/`conductor`/`pipeline`).
   State the goal: the script set works headless as plain executables **and** under the shell.
   Mark status **accepted, not yet implemented**; it reshapes Фаза 8 (panel) — reference
   [SPEC-panel.md](../SPEC-panel.md) and [ADR-0006](0006-panel-and-delivery.md). Add a BACKLOG
   item under «Потом» and a one-line pointer from SPEC-panel's script-editor section.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the deploy hooks are `Dockerfile`,
  `docker-compose.yml`, `pyproject.toml`, `alembic.ini`, `.env.example`, `app/cli.py` (command
  names only). Don't rescan app internals; the app is done through Фаза 6.
- **Portability, no secrets in the repo:** everything via `.env` / env; `.env` stays gitignored;
  the cookie store and PG data live in named volumes, never in the image.
- **Migrations on startup** via the entrypoint — never bake data; `alembic upgrade head` is
  idempotent.
- Runtime image runs **non-root** and can write `COOKIE_STORE_DIR`.
- **No `.github/workflows/**` edits** (local-only). **No installer, no hosting lock-in.**
- ADR-0008 is **documentation only** — no script restructuring in this PR.
- Code/comments/commits in English; owner-facing docs (`docs/OPS.md`, DEVLOG, BACKLOG, ROADMAP,
  ADR) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) stays green (no Python logic added; earlier
  phases' tests untouched and passing).
- `docker compose -f docker-compose.prod.yml build` succeeds; the **entrypoint applies
  `alembic upgrade head` then execs the command**; `command: ["serve"]` starts the APScheduler
  daemon; overriding the command to `run-once` / `metrics` / `warm-ozon` / `healthcheck` works.
- A documented **local smoke** works: `up` (postgres + app), migrations applied, `import-regions`
  + `import-products` load demo refs, `run-once` completes a run and writes rows, `metrics` prints
  the summary — all via the Makefile/compose (no live marketplace required for the smoke; the
  **live "боевой" run** against real WB/Ozon + proxies is the operator's manual step, documented).
- The runtime image is **non-root** and persists warmed cookies + PG data across restarts via
  named volumes.
- `docs/OPS.md` lets a fresh operator go clone → `.env` → migrations → warm cookies → `run-once`
  smoke → `serve` → read metrics/logs, with an explicit field-test checklist.
- `docs/adr/0008-script-shell-separation.md` records the rework (accepted, not implemented) with
  the planned scripts + orchestrator + shell role + Actions-like pipeline; `BACKLOG.md` has the
  «Потом» item; SPEC-panel's script-editor section points to it.
- `docs/DEVLOG.md` has a pass entry; `BACKLOG.md` marks Фаза 7 deploy-core done and keeps
  **installer** + **hosting choice** as open follow-ups; `docs/ROADMAP.md` notes Фаза 7 split into
  deploy-core (this) and installer (later).
- Merged into `main` via PR with the DoD gate green.
