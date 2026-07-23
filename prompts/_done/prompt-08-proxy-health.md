# prompt-08 — Proxy health / cooldown + anti-bot tuning

- **Branch:** `feat/proxy-health`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md) §Устойчивость к антиботу / §Нефункциональные требования,
  [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §Устойчивость к антиботу,
  [ROADMAP → Фаза 6](../docs/ROADMAP.md), [ADR-0003](../docs/adr/0003-proxy-provider.md),
  [ADR-0007](../docs/adr/0007-observability.md)

## Scope

This is the **second half** of Фаза 6 (the first half, observability, shipped in
`prompt-07-observability`). This slice makes collection **resilient**: a proxy-health / cooldown
policy behind the existing `ProxyProvider` seam, and anti-bot fine-tuning (request pacing / rate
limits + fingerprint variation). It builds on Фаза 5 orchestration and Фаза 6.1 observability —
health and cooldown are **derived from the `attempts` table** (owner's decision in
[ADR-0007](../docs/adr/0007-observability.md) §4: no new schema), and every decision is emitted
as a structured log event via the `app/obs` logging already in place.

**We do:**

1. **Proxy health, derived from `attempts` (no new schema).** A pure core
   `app/proxy/health.py::evaluate_health(...)` decides whether a `proxy_ref` is **cooling down**
   from recent attempt outcomes: given the count of `HARD_BAN` (and `SOFT_BAN`) attempts for that
   `proxy_ref` inside a sliding window and the timestamp of the last ban, it returns a
   `HealthVerdict(cooling_down: bool, until: datetime | None, ban_count: int)`. Cooling down when
   `ban_count >= settings.proxy_ban_threshold` within `settings.proxy_health_window_s`; the
   cooldown lasts until `last_ban_at + settings.proxy_cooldown_s`.

2. **`ProxyHealthService`** (`app/proxy/health.py`) — the DB read side: constructed from the
   `session_factory`, `async def verdict(region_code, proxy_ref) -> HealthVerdict` opens a short
   **read** session and aggregates the run-agnostic recent `attempts` for that `proxy_ref`
   (`attempts.proxy_ref == ref`, `outcome in (hard_ban, soft_ban)`, `created_at >= now - window`),
   then calls `evaluate_health`. No writes, no new table.

3. **`HealthAwareProxyProvider`** (`app/proxy/health.py`) — a **decorator** over any base
   `ProxyProvider` (keeps the seam; ADR-0003). `acquire(region_code)`: build the base lease, ask
   `ProxyHealthService.verdict(region, lease.ref)`; if cooling down, **raise `ProxyOnCooldown`**
   (carries `until`) — do **not** hammer a banned proxy, and do **not** silently fall back to a
   different-geo proxy (that would corrupt the regional price). `report(lease, outcome)` delegates
   to the base and emits a structured `proxy.health` event. Wire it into `make_proxy_provider`
   when `settings.proxy_health_enabled` (default `True`), wrapping the existing
   `StaticProxyProvider`.

4. **Cooldown → skip, cleanly (no fake ban, no new enum).** In
   `app/collectors/measure.py::measure_pair`, catch `ProxyOnCooldown` **before** the network call
   and return the existing `NEEDS_WARM`-style skip sentinel (`None`) — the caller marks the queue
   item without writing a fake `attempts` row, exactly like the Ozon "needs warm" path. Emit a
   structured `proxy.cooldown` event (region, `proxy_ref`, `until`). In the runner's retry loop
   (`_process_item`), a `None` outcome is already terminal (no retry) — a mid-retry cooldown after
   a `HARD_BAN` therefore stops retrying and skips, which is the intended "let it cool" behaviour.

5. **Anti-bot: request pacing / per-marketplace rate limit.** A process-global async limiter
   `app/collectors/pacing.py::RateLimiter` enforcing a **per-marketplace minimum interval + random
   jitter** between outbound requests (`settings.wb_min_interval_s`, `settings.ozon_min_interval_s`,
   `settings.request_jitter_s`). `measure_pair` `await`s `pacer.wait(marketplace)` before
   `collect`. A `NullRateLimiter` is the default so the CLI `measure-*` paths and tests are
   unaffected unless a real pacer is injected; `run_once` builds **one** shared `RateLimiter` and
   passes it to every worker (pacing must be shared across the pool, not per-worker).

6. **Anti-bot: fingerprint variation.** `app/collectors/fingerprint.py` centralizes the browser
   fingerprint: `wb_headers(region)` (today's `_HEADERS` from `wb.py`, plus consistent
   `sec-ch-ua*` and a UA chosen **deterministically per region** so a region keeps one identity
   across attempts) and `ozon_impersonate(region, settings)` (pick a `curl_cffi` impersonate
   target deterministically per region from a small allowed set, defaulting to
   `settings.ozon_impersonate`). `WbCollector` / `OzonCollector` consume these instead of the
   hardcoded constants. Consistency-per-region is the point — do **not** randomize per request.

7. **Docs cleanup (requested by the owner).** Bring the docs in line with the Фаза 6 split, which
   `prompt-07` left half-done:
   - `docs/ROADMAP.md` — **Фаза 6 still reads as one bundle `prompt-07-resilience`.** Rewrite it
     into two slices: **Фаза 6.1 — Наблюдаемость · `prompt-07-observability`** (done: metrics,
     structured logs, success-rate alert; DoD met) and **Фаза 6.2 — Здоровье прокси и антибот ·
     `prompt-08-proxy-health`** (this slice: proxy health/cooldown, pacing/rate-limit,
     fingerprint). Keep the phase-numbering and the "Порядок и зависимости" section coherent.
   - `prompts/README.md` — the "Активные" list is stale (still lists only `prompt-00-spike`);
     refresh it to reality (active prompts in root, done ones archived under `_done/`).
   - `BACKLOG.md` — tick **Фаза 6, часть 2** off on completion (the item already exists under
     «Потом» as `prompt-08-proxy-health`).

**We do NOT:**
- **no new schema / no migration** — health is read-derived from `attempts`; no `proxy_health`
  table, no new `Outcome` / `QueueStatus` / `RunStatus` values (cooldown reuses the skip sentinel);
- **no proxy rotation pool / no commercial provider integration** — `StaticProxyProvider` stays
  1 proxy per region; "health" here means cooldown+skip, not choosing among many IPs. A rotating
  commercial provider is still just another `ProxyProvider` behind the same seam (ADR-0003), added
  later without touching this code;
- **no CAPTCHA solving and no Playwright changes** — cookie warming (Ozon) is unchanged; this
  slice is about pacing, fingerprint consistency, and cooling banned proxies, not solving
  challenges;
- **no Prometheus endpoint / no alerting changes** — reuse `app/obs` from Фаза 6.1 as-is (just
  emit the new structured events);
- do not change the queue, retry/backoff math, parsers, cookie store, or the DB models — reuse
  everything on `main`.

## Body (concrete files/steps)

1. **Config** (`app/config.py`, mirror shapes into `.env.example`):
   - Proxy health: `proxy_health_enabled: bool = True`, `proxy_ban_threshold: int = 3`,
     `proxy_health_window_s: int = 900`, `proxy_cooldown_s: int = 1800`.
   - Anti-bot pacing: `wb_min_interval_s: float = 1.0`, `ozon_min_interval_s: float = 2.0`,
     `request_jitter_s: float = 0.5`.

2. **Proxy health** (`app/proxy/health.py`):
   - `@dataclass(frozen=True) HealthVerdict(cooling_down: bool, until: datetime | None, ban_count: int)`.
   - pure `evaluate_health(ban_count, last_ban_at, now, *, threshold, cooldown_s) -> HealthVerdict`.
   - `class ProxyOnCooldown(RuntimeError)` carrying `region_code`, `proxy_ref`, `until`.
   - `ProxyHealthService(session_factory, settings)` with `async def verdict(region_code, proxy_ref)`.
   - `HealthAwareProxyProvider(base: ProxyProvider, health: ProxyHealthService, settings)` —
     implements the `ProxyProvider` `Protocol`; `acquire` raises `ProxyOnCooldown` when cooling
     down, else returns the base lease; `report` delegates + logs `proxy.health`.
   - Extend `make_proxy_provider(settings, *, session_factory=None)` to wrap the base provider when
     `proxy_health_enabled and session_factory is not None`. When no factory is supplied (pure CLI
     `measure-*` without health), behaviour is unchanged.

3. **Wire health into the run** (`app/scheduler/runner.py`): pass `get_session` into the provider
   factory for the pool (`make_proxy_provider(settings, session_factory=session_factory)`), so
   workers get a `HealthAwareProxyProvider`. Everything else in `run_once` unchanged.

4. **Pacing** (`app/collectors/pacing.py`): `RateLimiter` (per-marketplace last-request timestamp
   + `asyncio.Lock`, `async def wait(marketplace)` sleeps to honour the min interval plus a random
   jitter in `[0, request_jitter_s]`), and a `NullRateLimiter` (`wait` returns immediately).
   `make_rate_limiter(settings)` builds the real one. `run_once` constructs one and threads it to
   workers → `measure_pair`.

5. **measure_pair** (`app/collectors/measure.py`): add an optional `pacer: RateLimiter = NullRateLimiter()`
   and, at the top of the try, `await pacer.wait(product.marketplace)`. Catch `ProxyOnCooldown`
   around `provider.acquire`, log `proxy.cooldown`, and return the skip sentinel (no attempt row).
   Keep the existing per-attempt `measurement` event; add `proxy_ref` / cooldown context to logs.

6. **Fingerprint** (`app/collectors/fingerprint.py`): `wb_headers(region) -> dict[str, str]` and
   `ozon_impersonate(region, settings) -> str`, deterministic per `region.code` (e.g. stable hash
   → index into a small allowed list). `WbCollector` uses `wb_headers(region)`; `OzonCollector`
   uses `ozon_impersonate(region, settings)` for the `impersonate=` argument. Preserve current
   defaults as one of the allowed identities so behaviour is stable and tests on the committed
   samples still pass.

7. **Tests** (no live network / no browser; DB tests skip cleanly without Postgres, per the
   Фаза 1/3/5 pattern with `TEST_DATABASE_URL`):
   - `tests/test_proxy_health.py` (pure): `evaluate_health` — below threshold → not cooling; at/above
     threshold within window → cooling until `last_ban_at + cooldown_s`; bans outside the window
     ignored; boundary at exactly `until`. A DB-gated case seeds `attempts` and asserts
     `ProxyHealthService.verdict`; a `HealthAwareProxyProvider.acquire` raises `ProxyOnCooldown`
     when the service reports cooling (service faked — no DB needed for that case).
   - `tests/test_pacing.py` (pure): `RateLimiter.wait` enforces the min interval per marketplace and
     stays within jitter bounds (patch/inject the clock and sleep — **no real sleeping**);
     `NullRateLimiter` never delays.
   - `tests/test_fingerprint.py` (pure): `wb_headers` / `ozon_impersonate` are deterministic per
     region (same region → same identity across calls; different regions may differ) and the
     default identity is within the allowed set.
   - Extend `tests/test_runner.py`: a stubbed provider that raises `ProxyOnCooldown` for a region
     makes that pair **skip without an attempt row** and marks the queue item terminal; metrics
     don't count it as a ban. Keep the Фаза 6.1 artificial-ban / alert assertions green.
   - Every earlier phase's test stays green.

## Constraints

- Model = Sonnet (pinned). **Minimal read scope** — the hooks are exactly:
  `app/proxy/base.py`, `app/proxy/static.py`, `app/collectors/measure.py`,
  `app/collectors/wb.py`, `app/collectors/ozon.py`, `app/scheduler/runner.py`, `app/config.py`,
  `app/repositories.py`, `app/enums.py`, `app/obs/`. Build on them; do not rescan the repo.
- **No schema change, no migration; no new `Outcome`/`QueueStatus`/`RunStatus`.** Cooldown reuses
  the existing skip sentinel (`None` from `measure_pair`), not a new enum value.
- **Keep the `ProxyProvider` seam clean** — health is a decorator, not a rewrite of
  `StaticProxyProvider`; a commercial rotating provider must still drop in behind the same
  `Protocol` (ADR-0003).
- **Correctness over coverage:** never measure a region through a different region's proxy or a
  cooled-down proxy to "get a number" — skip and let it cool. A cooled-down region is absent from
  the run, not wrong in it.
- **Best-effort side-channels:** a health-query failure or a pacing hiccup must never abort or roll
  back a run (mirror "one pair's failure never aborts the run"); on health-service error, fail open
  (treat as not cooling) and log it.
- Secrets & money never logged: only the masked `lease.ref`; `Decimal` price fields stay out of
  logs. Fingerprint variation must not leak proxy creds.
- Money stays `Decimal`; never float. Reuse `app/obs` logging for all new events
  (`proxy.cooldown`, `proxy.health`). Deterministic-per-region fingerprints — never per-request.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG/ROADMAP/ADR) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green. `test_proxy_health.py`,
  `test_pacing.py`, `test_fingerprint.py` and the runner cooldown-skip case run and pass; DB-backed
  tests skip cleanly **without** a DB and run **with** one (`TEST_DATABASE_URL`); every earlier
  phase's test stays green.
- **Proxy health works off `attempts` with no schema change:** after `proxy_ban_threshold`
  hard-bans for a `proxy_ref` inside `proxy_health_window_s`, `HealthAwareProxyProvider.acquire`
  raises `ProxyOnCooldown` until `last_ban_at + proxy_cooldown_s`; the pair is **skipped without a
  fake attempt**, emits `proxy.cooldown`, and is not counted as a ban in metrics — asserted by a
  test.
- **Anti-bot pacing** enforces a per-marketplace minimum interval + jitter between requests via one
  shared `RateLimiter` across the worker pool; CLI `measure-*` still work with the null limiter.
- **Fingerprints are consistent per region** (WB headers + Ozon impersonate), deterministic and
  within the allowed set; committed-sample parser tests remain green.
- **Docs cleaned up:** `docs/ROADMAP.md` splits Фаза 6 into 6.1 (`prompt-07-observability`, done)
  and 6.2 (`prompt-08-proxy-health`, this slice) with the ordering section coherent;
  `prompts/README.md` «Активные» reflects reality; `docs/DEVLOG.md` has a pass entry; `BACKLOG.md`
  ticks Фаза 6 часть 2.
- The TZ "Устойчивость к антиботу" requirement (ротация/остывание забаненных, человекоподобный
  темп, ретраи) is satisfied for MVP: banned proxies cool down, requests are paced, fingerprints
  are consistent per region.
- Merged into `main` via PR with the DoD gate green.
