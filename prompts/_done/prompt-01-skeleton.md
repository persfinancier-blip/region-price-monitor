# prompt-01 — Project skeleton & tooling

- **Branch:** `feat/skeleton`
- **Commit type:** `feat:` (skeleton may include `chore:` for tooling)
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ADR-0001](../docs/adr/0001-stack.md), [ADR-0004](../docs/adr/0004-scheduling-runtime.md), [ROADMAP → Фаза 0](../docs/ROADMAP.md)

## Scope

**We do:** stand up an empty-but-runnable Python 3.12 project skeleton with real tooling, config, DB connectivity, containerization, and a working DoD gate. No business logic yet.

**We do NOT:** implement any collector, proxy, scheduler, or DB models. No marketplace calls. Those are later phases.

## Body (concrete files/steps)

1. **Package layout** under `app/` (async): `app/__init__.py`, `app/config.py`, `app/db.py`, `app/cli.py`, plus empty `app/collectors/`, `app/proxy/`, `app/queue/`, `app/scheduler/` packages with `__init__.py` placeholders (interfaces land in later phases).
2. **`pyproject.toml`**: Python 3.12; deps — `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `requests`, `curl_cffi` (Ozon TLS-под-Chrome, ADR-0005), `playwright` (только прогрев кук), `apscheduler`, `structlog` (or `loguru`); dev — `ruff`, `mypy`, `pytest`, `pytest-asyncio`. Configure ruff + mypy (strict-ish) sections.
3. **Config** (`app/config.py`): pydantic-settings `Settings` reading `DATABASE_URL`, `SCHEDULE_CRON`, `MAX_CONCURRENCY`, `RETRY_LIMIT`, proxy placeholders. Provide **`.env.example`** with the shape; ensure `.env` stays gitignored.
4. **DB** (`app/db.py`): async engine + session factory from `DATABASE_URL`; a `healthcheck()` that runs `SELECT 1`.
5. **Alembic**: initialize `migrations/` wired to async engine + `app` metadata (metadata empty for now); `alembic upgrade head` must succeed on an empty schema.
6. **CLI** (`app/cli.py`): entrypoint with a `healthcheck` command that verifies DB connectivity and prints OK.
7. **Docker**: `Dockerfile` on the official Playwright Python base image; `docker-compose.yml` with services `app` and `postgres:16` (+ volume). `.dockerignore`.
8. **DoD gate** (`scripts/dod.sh`): replace the trivial stub with real checks — `ruff check .`, `ruff format --check .`, `mypy app`, `pytest -q`. Keep it POSIX `sh`.
9. **Smoke test** (`tests/test_healthcheck.py`): trivial passing test so `pytest` and the gate are green from day one.

## Constraints

- Model = Sonnet (pinned). Minimal read scope; do not scan the whole repo.
- Secrets never committed; `.env` gitignored, only `.env.example` holds the shape.
- Code/comments/commits in English; owner-facing docs in Russian (per CLAUDE.md).
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` runs ruff + mypy + pytest and exits green.
- `docker compose up` brings up `app` and `postgres`; `cli healthcheck` reports DB OK against the compose postgres.
- `alembic upgrade head` succeeds on an empty database.
- `.env.example` present; `.env` gitignored; no secrets in the diff.
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` item for Фаза 0 checked off.
- Merged into `main` via PR with the DoD gate green.

<!-- re-dispatched for Фаза 0 (skeleton), attempt 2, 2026-07-22 -->
