# prompt-05 — Ozon collector (curl_cffi + warmed cookies + cookie warming)

- **Branch:** `feat/ozon-collector`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 4](../docs/ROADMAP.md), [ADR-0005](../docs/adr/0005-scraping-method-update.md), [ADR-0003](../docs/adr/0003-proxy-provider.md)

## Scope

**We do:** ship the Ozon price collector per ADR-0005 — `OzonCollector` reading the
composer-api price endpoint via **`curl_cffi` with `impersonate="chrome"`** and **warmed
cookies**, plus the **cookie-warming component** (Playwright, one-time manual captcha/city
solve, saves `storage_state`) and a **filesystem cookie store** keyed by
`(marketplace × region_code)` with `warmed_at` + TTL metadata behind a `CookieStore`
abstraction. Region is resolved by the **hybrid** model (owner decision 2026-07-23): by
default the region is carried by the warmed cookie and the fetch goes direct (`proxy_url=None`);
a city may be given a **personal proxy** via the existing `StaticProxyProvider` /
`proxy_map_json`, and then both warming and fetch route through that proxy. Wire Ozon into the
same `run` / `measure_queue` / `attempts` / `price_snapshot` flow already on `main`, classify
each try's `Outcome`, and on a 403/anti-bot outcome mark the cookie bundle stale so it is
re-warmed.

**We do NOT:**
- headless/Xvfb warming on a server — warming this phase runs a **visible browser via
  `MANUAL=1`** (server-side headless warming is Фаза 7 / [ADR-0006](../docs/adr/0006-panel-and-delivery.md));
- scheduler / APScheduler, concurrent queue claim (`FOR UPDATE SKIP LOCKED`) or worker-pool
  concurrency (Фаза 5);
- retry/backoff policy, proxy health/cooldown, metrics/alerts (Фаза 6);
- panel/API, and cookie **encryption** or a DB-backed cookie store (Фаза 8 — filesystem this
  phase);
- isolating *which single cookie* carries the region — store the **full warmed cookie set** per
  city (ADR-0005 open question), do not try to reduce it;
- a real commercial proxy provider — reuse `StaticProxyProvider`.
Reuse the schema, collector base, proxy abstraction, repos and CLI already on `main` — do not
re-model anything.

## Body (concrete files/steps)

1. **Deps** (`pyproject.toml`): add `curl_cffi` (routine Ozon fetch) and `playwright`
   (warming only). The Playwright browser binary download is a warming-time / deploy concern
   (Фаза 7) — do **not** make CI depend on downloading a browser.

2. **Config** (`app/config.py`): add `ozon_api_url: str = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"`,
   `ozon_impersonate: str = "chrome"`, `cookie_store_dir: str = "data/cookies"`, and
   `ozon_cookie_ttl_hours: int = 12` (TTL is **time-based** per owner intuition — a config knob,
   measured for real on the live prototype). Add the shapes (not values) to `.env.example`.
   Ensure `data/**` is gitignored (cookie files never enter the repo).

3. **Cookie store** (`app/cookies/base.py` + `app/cookies/fs.py`):
   - Frozen dataclass `CookieBundle`: `marketplace: Marketplace`, `region_code: str`,
     `storage_state: dict[str, Any]` (Playwright `storage_state`), `warmed_at: datetime`,
     `stale: bool = False`, `source_ref: str | None = None` (non-secret label of the warm IP,
     e.g. `"direct"` / `"static:ekb:host"`).
   - `CookieStore` Protocol: `load(marketplace, region_code) -> CookieBundle | None`,
     `save(bundle) -> None`, `mark_stale(marketplace, region_code) -> None`, and a pure
     `is_stale(bundle, ttl_hours) -> bool` (True when `warmed_at + ttl < now` **or** the
     `stale` flag is set).
   - `FsCookieStore`: one JSON file per `cookie_store_dir/{marketplace}/{region_code}.json`.
     Never log cookie contents; path is under gitignored `data/**`. A
     `make_cookie_store(settings)` factory (only `fs` this phase).

4. **Warming component** (`app/cookies/warm.py`): productionize `spike/check_ozon.py`.
   - `CookieWarmer.warm(marketplace, region)` opens a real Chromium via Playwright, applies the
     region's city hint from `region.geo["ozon"]` (so the resulting `storage_state` carries the
     region), waits for the operator to pass captcha / confirm the city in `MANUAL=1` mode,
     captures `storage_state`, and writes a fresh `CookieBundle` via the store.
   - If the region has a proxy (its `proxy_map_json` entry / `geo["ozon"]` override), the browser
     is launched **through that proxy** so warm-IP == fetch-IP for that city (hybrid); otherwise
     direct.
   - Orchestration: `warm_if_stale(store, warmer, marketplace, region, ttl_hours)` re-warms only
     when missing/stale; a `warm-ozon` CLI command warms all active Ozon regions (or `--region`).

5. **Ozon parser** (`app/collectors/ozon_parse.py`, pure): parse the composer-api JSON into a
   `PriceObservation`. Find the `webPrice*` widget in `widgetStates` (JSON-in-JSON, values are
   JSON strings — parse them): `price` → `PriceObservation.price`, `originalPrice` (no card) →
   `price_base`, `cardPrice` → `price_card`; `currency="RUB"`; derive `is_available` from
   stock/out-of-stock widget presence. On an empty / anti-bot / captcha page raise a typed
   `OzonParseError` so classification can see it. Unit-testable over a committed sample; add a
   captured composer-api fixture under `tests/data/`.

6. **Ozon collector** (`app/collectors/ozon.py`): `OzonCollector` implementing
   `MarketplaceCollector` — `marketplace = Marketplace.OZON`,
   `collect(self, product, region, proxy_url=None) -> PriceObservation`.
   - Load the `CookieBundle` for `(OZON, region.code)`; if missing or stale raise a typed
     `OzonCookiesUnavailable` **before any network call** (the CLI turns this into a warm request,
     not a failed HTTP try).
   - Fetch with `curl_cffi.requests.get(settings.ozon_api_url, params={"url": f"/product/{product.sku}/"}, impersonate=settings.ozon_impersonate, cookies=…, proxies=proxy_url_to_requests_dict(proxy_url), timeout=settings.http_timeout_s)`.
     **Plain `requests` returns 403 — `curl_cffi` impersonation is mandatory (ADR-0005).**
   - Non-200 / anti-bot → raise `OzonCollectionError(status_code=…, anti_bot=…)`, mirroring
     `WbCollectionError`; else return `parse_ozon(response.json())`.

7. **Outcome classification** (`app/collectors/outcome.py`, pure): extend the existing classifier
   for Ozon — 200 + parsed → `OK`; 403/429 or anti-bot/captcha page → `HARD_BAN`; `curl_cffi`
   timeout → `TIMEOUT`; other transport error → `ERROR`; valid-but-suspicious (documented
   trigger) → `SOFT_BAN`. Do **not** add new `Outcome` values (the enum is fixed). Cookie
   unavailability is handled in the CLI (warm path), not as an attempt outcome.

8. **Repositories**: reuse `MeasureQueueRepository`, `AttemptRepository` and the snapshot repo
   from Фаза 3 as-is — **no new tables**.

9. **CLI** (`app/cli.py`): add `measure-ozon`, mirroring `measure-wb`. `--region` repeatable /
   optional (default: all active regions that have active Ozon products); `--sku` optional
   (default: all active Ozon products). Per `(product, region)`: `warm_if_stale` (interactive
   only — non-interactive run reports "needs warm" and skips the pair without a fake attempt);
   create a `measure_queue` row; `acquire` a proxy lease (default direct); time the try; run
   `collector.collect(product, region, lease.proxy_url)` via `asyncio.to_thread`; classify the
   `Outcome`; on `OK` write the `price_snapshot`; on `HARD_BAN` call `store.mark_stale(OZON,
   region.code)`; always write an `attempts` row (`proxy_ref = lease.ref`, `duration_ms`, `error`
   on failure); `mark` the queue item `done`/`failed`; `await provider.report(lease, outcome)`.
   One pair's failure never aborts the run; finish the `run` with `stats` = counts per outcome;
   print a compact per-region summary. Also add the `warm-ozon` command from step 4.

10. **Tests** (no live network, no browser in CI):
    - `tests/test_ozon_parse.py` — parser over the committed composer-api fixture → correct
      `price` / `price_base` / `price_card` / `is_available`; anti-bot/empty page → `OzonParseError`.
    - `tests/test_cookie_store.py` — `FsCookieStore` save/load round-trip (tmp dir); `is_stale`
      True by TTL expiry and by explicit `stale` flag, False when fresh; `mark_stale` flips it.
    - `tests/test_outcome.py` — extend: Ozon 200→`OK`, 403→`HARD_BAN`, timeout→`TIMEOUT`,
      transport→`ERROR`.
    - Playwright warming and live `curl_cffi` calls are **not** exercised in CI (guard/skip).
      Keep all earlier phases' tests green.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — method is [ADR-0005](../docs/adr/0005-scraping-method-update.md),
  proxy contract is [ADR-0003](../docs/adr/0003-proxy-provider.md); collector base, proxy,
  config, models, repos and CLI are on `main`. Build on them, don't rescan the repo.
- **`curl_cffi` `impersonate` is mandatory for Ozon** — plain `requests` = 403 (JA3
  fingerprinting). Do not "simplify" it back to `requests`.
- **Region = cookie by default; proxy is an optional per-city layer** (hybrid, ADR-0005). No
  parallel region-via-IP path for Ozon.
- Cookies / `storage_state` and any proxy credentials **never** touch the repo, logs, or
  `attempts.proxy_ref` — cookie files live under gitignored `data/**`; `.env.example` holds
  shape, not values; `proxy_ref` stays a masked, non-secret label.
- No concurrency / no `SKIP LOCKED` here (Фаза 5). Money stays `Decimal`; never float.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy + pytest) exits green; `test_ozon_parse.py`,
  `test_cookie_store.py` and the extended `test_outcome.py` run (not skipped) and pass in CI
  with no network and no browser; DB-backed tests skip cleanly without a DB; earlier phases'
  tests stay green.
- `OzonCollector.collect` fetches via `curl_cffi` impersonation with the region's warmed
  cookies; with `proxy_url` set it routes through that proxy, and with `proxy_url=None` it goes
  direct (the cookie carries the region).
- The cookie store persists a warmed `storage_state` per `(marketplace × region_code)`;
  `is_stale` is driven by `ozon_cookie_ttl_hours` and by the explicit stale flag; a 403/anti-bot
  measure marks the bundle stale; `warm-ozon` re-warms it.
- `measure-ozon` with no `--region` measures an Ozon SKU across all active regions, writing a
  `measure_queue` row and an `attempts` row per pair (outcome recorded) and a `price_snapshot`
  on success; `run.stats` aggregates outcomes.
- Manual/local check (not part of the CI gate): with cookies warmed for two cities (e.g. msk,
  ekb), the same Ozon SKU yields **region-differing `cardPrice` via cookies alone** (no proxy);
  giving one city a `proxy_map_json` entry routes its warm+fetch through that proxy.
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` Фаза 4 item checked off, and the two
  open questions updated: region-cookie → "store the full warmed set per city"; TTL →
  "`ozon_cookie_ttl_hours`, time-based, to be measured on the live prototype".
- Merged into `main` via PR with the DoD gate green.
