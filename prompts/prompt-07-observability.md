# prompt-07 — Observability (metrics + structured logs + success-rate alert)

- **Branch:** `feat/observability`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md) §Наблюдаемость / §Нефункциональные требования, [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §Observability, [ROADMAP → Фаза 6](../docs/ROADMAP.md)

## Scope

This is the **first half** of Фаза 6, split by the owner into two slices. This slice ships
**observability only**: run metrics, structured logs, and a success-rate alert. The **second
half** — proxy health / cooldown policy and anti-bot fine-tuning — is a separate `prompt-08`
and is explicitly **out of scope here**.

**We do:** turn today's silent, `print`-only runs into an observable pipeline over the code
already on `main` (Фаза 5 orchestration).

1. **Structured logging** — a JSON log setup (`app/obs/logging.py`) wired into the CLI entry
   point, plus **one structured per-attempt event** emitted from the single shared measurement
   unit `app/collectors/measure.py::measure_pair` (it already holds all the context: run_id,
   marketplace, product, region, proxy_ref, outcome, duration_ms). Run-level `run.started` /
   `run.finished` events from `app/scheduler/runner.py::run_once`.

2. **Run metrics** — a pure `app/obs/metrics.py` that **derives** metrics from data already in
   Postgres (owner's decision: no new schema, no exporter server). For a `run_id` it aggregates
   the `attempts` of that run (join `attempts.queue_id → measure_queue.id`, filter
   `measure_queue.run_id`) into a frozen `RunMetrics`: `total`, per-`Outcome` counts,
   `success_rate`, `ban_rate`, `error_rate`, `avg_duration_ms`, and `attempts_per_success` (the
   MVP proxy for **cost per successful measure** — total attempts ÷ OK count; a real monetary
   hook lands with the commercial proxy provider later). A `metrics` CLI command prints them
   human-readable **and** in Prometheus text-exposition format (Prometheus-ready without a live
   endpoint) **and** as one structured log line.

3. **Success-rate alert** — an `Alerter` seam (`app/obs/alerts.py`, owner's decision) mirroring
   the `ProxyProvider` pattern: a `Protocol` + a default `LogAlerter` (structured WARN/ERROR to
   the log/stderr) + an optional vendor-agnostic `WebhookAlerter` (POSTs JSON to a configured
   URL). A pure `should_alert(metrics, threshold, min_measures)` decides; `run_once` evaluates
   it after finalizing the run and fires the alert when the success rate drops below
   `settings.success_rate_threshold` (KPI ≥ 0.9 per TZ).

4. **ADR + docs** — record the four decisions taken with the owner in a short
   `docs/adr/0007-observability.md`; update `docs/DEVLOG.md` and `BACKLOG.md`.

**We do NOT:**
- **proxy health / cooldown / rotation policy** and **anti-bot fine-tuning** (rate limits,
  jitter, fingerprint tuning) — that is `prompt-08` (second half of Фаза 6). `StaticProxyProvider.report`
  stays a no-op here; do not add health scoring. (prompt-08 will derive proxy health from the
  same `attempts` table — keep the per-attempt `proxy_ref` logging clean so it can.)
- **no Prometheus HTTP endpoint / exporter daemon** — metrics are DB-derived + structured logs +
  Prometheus **text** output from the `metrics` CLI. A live `/metrics` endpoint belongs to the
  panel / deploy phases (Фаза 7–8);
- **no new alerting vendor hardcoded** — Telegram/Slack/etc. are just a `WebhookAlerter` URL;
  no vendor SDK, no creds in the repo;
- **no schema change / no migration** — metrics come from existing `runs` and `attempts`; **no
  new `Outcome` / `QueueStatus` / `RunStatus` values**;
- do not change collectors, parsers, the proxy or cookie abstractions, the queue, or retry/backoff
  logic — this slice observes what Фаза 5 already does. Reuse models, repos, enums, runner as-is.

## Body (concrete files/steps)

1. **Config** (`app/config.py`): add observability knobs (keep the existing style, defaults in
   code, shapes mirrored into `.env.example`):
   - `log_level: str = "INFO"`, `log_format: str = "json"` (`json` | `text`).
   - `success_rate_threshold: float = 0.9`, `alert_min_measures: int = 1` (never alert on a
     run smaller than this — avoids false alarms on tiny/warm-up runs).
   - `alerter: str = "log"` (`log` | `webhook`), `alert_webhook_url: str | None = None`.

2. **Structured logging** (`app/obs/__init__.py`, `app/obs/logging.py`): a stdlib-only JSON
   `logging.Formatter` (no new runtime dependency) that serializes level, logger, message,
   timestamp, and any `extra` fields; `configure_logging(settings)` installs it on the root
   logger (or plain text when `log_format="text"`). Call `configure_logging(get_settings())`
   once at the top of `app/cli.py::main`. **Never log secrets or raw proxy URLs** — only the
   already-masked `lease.ref`; **never log money** (`Decimal` price fields stay out of logs).

3. **Per-attempt event** (`app/collectors/measure.py`): after `classify_outcome`, emit a single
   structured log line (e.g. `logger.info("measurement", extra={...})`) with `run_id`,
   `marketplace`, `product_id`, `sku`, `region_code`, `proxy_ref` (masked), `outcome`,
   `duration_ms`, and `error` when present. This is the **one** place per-attempt telemetry is
   produced — the CLI and the worker pool both go through `measure_pair`, so both get it for
   free. Behaviour and return value of `measure_pair` are otherwise unchanged.

4. **Metrics** (`app/obs/metrics.py`):
   - `@dataclass(frozen=True) RunMetrics` with the fields listed in Scope §2.
   - Pure `metrics_from_counts(counts: dict[str, int], total_duration_ms: int) -> RunMetrics` so
     the arithmetic is unit-tested without a DB (rates guard divide-by-zero; `attempts_per_success
     = total / ok` with `ok == 0 → total` as the worst-case proxy, documented).
   - `async def compute_run_metrics(session, run_id) -> RunMetrics`: aggregate the run's
     `attempts` via the `attempts.queue_id → measure_queue.id` join filtered by `run_id`
     (`func.count` grouped by `outcome`, `func.coalesce(func.sum(duration_ms), 0)`), then call
     `metrics_from_counts`.
   - `to_prometheus(metrics, run_id) -> str`: Prometheus text-exposition lines
     (`rpm_run_success_rate{run_id="…"} 0.87`, per-outcome counters, `rpm_run_attempts_per_success`,
     etc.). No `prometheus_client` dependency — plain string.

5. **Alerts** (`app/obs/alerts.py`):
   - `@dataclass(frozen=True) Alert` (`kind`, `run_id`, `success_rate`, `threshold`, `message`).
   - `class Alerter(Protocol): async def send(self, alert: Alert) -> None`.
   - `LogAlerter` — structured `logger.warning`/`error`. `WebhookAlerter(url)` — `requests.post`
     (already a dependency) wrapped in `asyncio.to_thread`, JSON body from the `Alert`, short
     timeout, failures logged but **never abort the run**.
   - `pure should_alert(metrics: RunMetrics, threshold: float, min_measures: int) -> bool`
     (`total >= min_measures and success_rate < threshold`).
   - `make_alerter(settings) -> Alerter` (`log` default; `webhook` requires `alert_webhook_url`,
     else explicit error — mirror `make_proxy_provider`).

6. **Runner integration** (`app/scheduler/runner.py`): in `run_once`, emit `run.started` at the
   top and, after `run_repo.finish`, open a read session, `compute_run_metrics(run_id)`, emit a
   `run.finished` structured event carrying the metrics, then `alerter = make_alerter(settings)`
   and `if should_alert(...): await alerter.send(Alert(...))`. Alerting must never roll back or
   fail the run. Extend `RunSummary` with the `RunMetrics` (or keep `stats` and add `metrics`)
   so the CLI can print it.

7. **CLI** (`app/cli.py`): `configure_logging` in `main`; add a `metrics` command
   (`--run <id>` or `--last` = most recent run) that loads a session, `compute_run_metrics`, and
   prints the human summary + `to_prometheus(...)`; keep the existing one-line run summary in
   `run-once` / `measure-*`.

8. **Tests** (no live network; DB tests skip cleanly without Postgres, following the Фаза 1/3/5
   pattern with `TEST_DATABASE_URL`):
   - `tests/test_metrics.py` — `metrics_from_counts` and `to_prometheus` are pure: correct
     `success_rate` / `ban_rate` / `error_rate` / `avg_duration_ms` / `attempts_per_success`,
     divide-by-zero guarded, Prometheus lines well-formed. A DB-gated case builds a run with
     mixed `attempts` and asserts `compute_run_metrics`.
   - `tests/test_alerts.py` — `should_alert` true below threshold, false at/above, false when
     `total < alert_min_measures`; `LogAlerter` logs (via `caplog`); `WebhookAlerter` posts the
     expected JSON with `requests.post` monkeypatched (assert URL + payload, **no real network**);
     a webhook failure does not raise.
   - `tests/test_logging.py` — the JSON formatter emits valid JSON with the expected keys and
     `extra` fields; assert **no** price/`Decimal` value and **no** raw proxy URL leak into a
     record built from a representative `extra`.
   - **Artificial-ban scenario** (add to `tests/test_runner.py` or a focused test): a stubbed
     collector that raises a ban is retried up to `retry_limit`, and the resulting metrics show
     `ban_rate > 0` and `attempts_per_success > 1`; below-threshold success fires the alerter
     exactly once (spy/fake `Alerter`), at/above fires zero times.
   - Keep every earlier phase's test green.

## Constraints

- Model = Sonnet (pinned). **Minimal read scope** — the hooks are exactly:
  `app/collectors/measure.py`, `app/scheduler/runner.py`, `app/config.py`, `app/cli.py`,
  `app/repositories.py`, `app/enums.py`, `app/models.py`. Build on them; do not rescan the repo.
- **No schema change, no migration**; metrics derive from existing `runs` + `attempts`. No new
  `Outcome` / `QueueStatus` / `RunStatus` members.
- **Stdlib-only structured logging and Prometheus text** — do not add `prometheus_client`,
  `structlog`, or an alerting-vendor SDK. `requests` (already present) is the only thing the
  webhook needs.
- **Secrets & money never logged:** only the masked `lease.ref`; `Decimal` price fields stay out
  of logs and out of alert payloads.
- Alerting and metrics are **best-effort side-channels**: a failure there must never abort or roll
  back a run (mirror "one pair's failure never aborts the run").
- Money stays `Decimal`; never float. Keep the `Alerter` seam clean so a real channel is a drop-in
  later without touching the runner.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG/ADR) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green. `test_metrics.py`, `test_alerts.py`,
  `test_logging.py` and the artificial-ban assertions run and pass; DB-backed tests skip cleanly
  **without** a DB and run **with** one (`TEST_DATABASE_URL`); earlier phases' tests stay green.
- `run-once` (and `serve`'s scheduled runs) produce structured JSON logs: a per-attempt
  `measurement` event and `run.started` / `run.finished` events; `run.finished` carries the run's
  metrics. No secret or price value appears in any log line.
- `metrics --last` / `metrics --run <id>` prints the human summary **and** valid Prometheus text
  derived from `runs`/`attempts` (no schema change).
- **Artificial ban** is retried per `retry_limit` and **reflected in metrics** (`ban_rate > 0`,
  `attempts_per_success > 1`) — asserted by a test.
- **Alert threshold fires:** success rate below `success_rate_threshold` (and `total >=
  alert_min_measures`) invokes `Alerter.send` exactly once; at/above threshold it does not — both
  asserted. Default `LogAlerter` needs no config; `WebhookAlerter` is opt-in via
  `alert_webhook_url`, vendor-agnostic.
- `docs/adr/0007-observability.md` records the four decisions (metrics from DB + structured logs;
  no Prometheus endpoint yet; `Alerter` seam with log default + optional webhook; proxy health &
  anti-bot deferred to `prompt-08`). `docs/DEVLOG.md` has a pass entry; `BACKLOG.md` reflects the
  Фаза 6 split (07 observability done, 08 proxy/anti-bot pending); the TZ "доля успеха → алерт"
  requirement is satisfied.
- Merged into `main` via PR with the DoD gate green.
