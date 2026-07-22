# prompt-04 — Regionalization + ProxyProvider (WB across regions)

- **Branch:** `feat/regions-proxy`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 3](../docs/ROADMAP.md), [ADR-0003](../docs/adr/0003-proxy-provider.md), [ADR-0005](../docs/adr/0005-scraping-method-update.md)

## Scope

**We do:** introduce the `ProxyProvider` abstraction (ADR-0003) and route WB collection
through it, so one WB product is measured across **several regions**, each via its region's
proxy, and every try is recorded in `attempts`. Ship a provider-agnostic interface plus a
`StaticProxyProvider` (config-driven, no external calls) — **no specific vendor is
hardcoded**; a commercial provider is just another implementation added later. Classify the
outcome of each try (`ok` / `soft_ban` / `hard_ban` / `timeout` / `error`) and feed it back
via `ProxyProvider.report(...)`.

**We do NOT:** implement a real commercial provider (only the interface + `StaticProxyProvider`
this phase), Ozon / `curl_cffi` / cookie warming (Фаза 4), the scheduler / APScheduler, the
**concurrent** queue claim (`FOR UPDATE SKIP LOCKED`) or worker-pool concurrency (Фаза 5),
retry/backoff policy tuning or proxy-health/cooldown strategy (Фаза 6). No panel/API. Reuse
the schema, collector, and repos already on `main` — do not re-model anything.

### Scope decision (queue + attempts, recorded here)

`attempts.queue_id` is a NOT-NULL FK to `measure_queue`, so to record attempts this phase the
manual run must create `measure_queue` rows. Фаза 3 therefore populates the queue
**sequentially** (one row per `(run, product, region)`, walked in a plain loop) and writes an
`attempts` row per try. The **concurrent** claim (`SKIP LOCKED`), worker pool, scheduler, and
retry/health policy stay in Фаза 5/6 — this phase only adds straight-line bookkeeping, no
locking or concurrency.

## Body (concrete files/steps)

1. **Proxy interface** (`app/proxy/base.py`): `RegionCode = str`. A frozen dataclass
   `ProxyLease` with `provider: str`, `region_code: str`, `proxy_url: str | None` (full
   `http://user:pass@host:port`, or `None` = direct), and `ref: str` — a **non-secret**
   identifier for `attempts.proxy_ref` (e.g. `"static:msk:host"`), **never** the credentials.
   Define `ProxyProvider` as a `typing.Protocol` matching ADR-0003:
   `async def acquire(self, region_code: RegionCode) -> ProxyLease` and
   `async def report(self, lease: ProxyLease, outcome: Outcome) -> None`. Add a small helper to
   turn `proxy_url` into a `requests` proxies dict (`{"http": url, "https": url}` or `None`).

2. **StaticProxyProvider** (`app/proxy/static.py`): built from config, no network. Resolves a
   region code to a proxy URL from a `{region_code: proxy_url}` map (config, step 3); unknown
   region → fall back to a single global `proxy_url` if set, else a direct (`None`) lease.
   `acquire` returns the `ProxyLease` (compute a masked `ref` from host, no creds). `report`
   is a no-op that logs at debug this phase (health/rotation is Фаза 6). A
   `make_proxy_provider(settings)` factory picks the implementation by `settings.proxy_provider`
   (`"static"` supported now; unknown value → clear error).

3. **Config** (`app/config.py`): keep `proxy_provider` and `proxy_url`; add
   `proxy_map_json: str | None = None` — a JSON object string `{"msk": "http://…", …}` parsed
   into a dict by the provider (invalid JSON → clear error at construction). Credentials come
   only from env; add the shape (not real values) to `.env.example`.

4. **Collector** (`app/collectors/wb.py`): extend `WbCollector.collect` signature to
   `collect(self, product, region, proxy_url: str | None = None)` and pass
   `proxies=` to `requests.get`. Default `None` keeps Фаза 2 behavior (direct). The regional
   price mechanism (`dest` from `region.geo["wb"]`) already works — keep it; the proxy adds the
   regional exit IP. `MarketplaceCollector.collect` in `base.py` gains the optional `proxy_url`
   param.

5. **Outcome classification** (`app/collectors/outcome.py`, pure): map a completed/failed try to
   an `Outcome` — HTTP 200 + parsed → `OK`; HTTP 403/429 (or WB anti-bot/empty body) →
   `HARD_BAN`; a `requests.Timeout` → `TIMEOUT`; other network/transport errors → `ERROR`;
   reserve `SOFT_BAN` for a valid-but-suspicious response (document the chosen trigger, e.g.
   200 with empty `products`). Pure function over (status/exception/parse-result) → `Outcome`,
   unit-testable with no network.

6. **Repositories** (`app/repositories.py`): add `MeasureQueueRepository`
   (`create(run_id, product_id, region_id) -> MeasureQueueItem` with `status=pending`;
   `mark(item, status)`), and `AttemptRepository`
   (`add(queue_id, proxy_ref, outcome, error, duration_ms) -> Attempt`). Keep the Фаза 2 repos
   as-is.

7. **CLI** (`app/cli.py`): extend `measure-wb`. `--region CODE` becomes repeatable /
   optional — default: **all active regions**; `--sku` optional as before (default: all active
   WB products). Flow per `(product, region)`: create a `measure_queue` row; `acquire` a proxy
   lease for the region; time the try; run `collector.collect(product, region, lease.proxy_url)`
   via `asyncio.to_thread`; classify the `Outcome`; on `OK` write the `price_snapshot`; always
   write an `attempts` row (`proxy_ref = lease.ref`, `duration_ms`, `error` on failure);
   `mark` the queue item `done`/`failed`; `await provider.report(lease, outcome)`. A failure on
   one pair never aborts the run. Finish the `run` with `stats` = counts per outcome. Print a
   compact per-region summary line.

8. **Tests** (no live network):
   - `tests/test_proxy_static.py` — `StaticProxyProvider`: region present in map → correct
     `proxy_url` + masked `ref` (no credentials in `ref`); unknown region → global fallback,
     then direct (`None`); invalid `proxy_map_json` → clear error.
   - `tests/test_outcome.py` — the classifier: 200-ok→`OK`, 403/429→`HARD_BAN`,
     timeout→`TIMEOUT`, transport error→`ERROR`, empty-`products`→`SOFT_BAN` (or the documented
     trigger).
   - Keep `tests/test_wb_parse.py` green. A DB-backed test that `measure-wb` writes
     `measure_queue` + `attempts` (+ a snapshot on ok) may reuse the Фаза 1 skip-without-DB
     pattern. Do not add a test that hits the live WB network or a real proxy in CI.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — `ProxyProvider` contract is in
  [ADR-0003](../docs/adr/0003-proxy-provider.md); collector/config/CLI/models/repos are on
  `main`. Build on them, don't rescan the repo.
- **Provider-agnostic:** no vendor name or vendor-specific API in code this phase — only the
  interface + `StaticProxyProvider`. A commercial provider is a future `ProxyProvider`
  implementation.
- Proxy **credentials never touch the repo, logs, or `attempts.proxy_ref`** — env/secrets only;
  `.env.example` holds shape, not values. `proxy_ref` is a masked, non-secret label.
- No concurrency / no `SKIP LOCKED` here (Фаза 5). Money stays `Decimal`; never float.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy + pytest) exits green; `test_proxy_static.py`,
  `test_outcome.py`, `test_wb_parse.py` run (not skipped) and pass in CI with no network;
  DB-backed tests skip cleanly when no DB; earlier phases' tests stay green.
- `WbCollector.collect(..., proxy_url=...)` routes the request through the given proxy; with
  `proxy_url=None` it behaves exactly as Фаза 2 (direct).
- `measure-wb` with no `--region` measures one WB product across all active regions, writing a
  `measure_queue` row and an `attempts` row per pair (outcome recorded) and a `price_snapshot`
  on success; `run.stats` aggregates outcomes.
- Manual/local check (not part of the CI gate): with real per-region proxies configured via
  `proxy_map_json`, the same WB SKU yields **region-differing prices**, and swapping the proxy
  for a region is reflected in the recorded attempt.
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` Фаза 3 item checked off (and the
  proxy-provider open question noted as: any provider — interface-first, `StaticProxyProvider`
  shipped).
- Merged into `main` via PR with the DoD gate green.
