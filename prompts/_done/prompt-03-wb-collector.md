# prompt-03 — WB collector (single home region, no proxy)

- **Branch:** `feat/wb-collector`
- **Commit type:** `feat:`
- **Docs:** [docs/TZ.md](../docs/TZ.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP → Фаза 2](../docs/ROADMAP.md), [ADR-0005](../docs/adr/0005-scraping-method-update.md)

## Scope

**We do:** the first end-to-end collection slice — a `MarketplaceCollector` interface and a
`WbCollector` implementation on `requests` (ADR-0005, endpoint `card.wb.ru`). Given a WB
`Product` and a `Region`, read the current price/availability from the WB card endpoint,
parse it into a typed observation, and persist a `price_snapshot` row tied to a `run`. One
manual run writes a real WB price for one **home** region — still a direct connection, **no
proxy**. The price-parsing logic is split out and unit-tested against a committed sample
response so it runs in CI without network.

**We do NOT:** touch proxies (`ProxyProvider` lands in Фаза 3), Ozon / `curl_cffi` / cookie
warming (Фаза 4), the scheduler, the queue, or `SKIP LOCKED` (Фаза 5). No multi-region
fan-out, no retries/ban handling policy, no panel/API. The `attempts` table is not written
this phase. Reuse the schema and repositories already on `main` from Фаза 1 — do not
re-model anything.

## Body (concrete files/steps)

1. **Observation DTO** (`app/collectors/base.py`): a frozen dataclass `PriceObservation`
   with `price: Decimal`, `price_base: Decimal`, `price_card: Decimal | None`,
   `currency: str`, `is_available: bool`, `raw: dict[str, Any]`. Money as `Decimal`, never
   float. Define the collector contract as a `typing.Protocol` (or ABC)
   `MarketplaceCollector` with `marketplace: Marketplace` and
   `collect(self, product: Product, region: Region) -> PriceObservation`. Keep it sync — the
   HTTP call is `requests`; the async DB layer wraps it (step 5).

2. **WB parser** (`app/collectors/wb_parse.py`, pure function, no I/O):
   `parse_wb_card(payload: dict) -> PriceObservation`. Target the `card.wb.ru` v2 shape:
   response is `{"data": {"products": [ … ]}}` (tolerate a missing `data` wrapper —
   `payload.get("data", payload)`); take `products[0]`; read price from
   `products[0]["sizes"][0]["price"]` where `basic`/`product`/`total` are **integer kopecks**
   (divide by 100 → `Decimal`). Map: `price_base = basic/100` (pre-discount),
   `price = product/100` (displayed sale price), `price_card = None` this phase (the WB-wallet
   price is computed client-side and not in this endpoint — document the choice in a
   comment). `currency = "RUB"`. `is_available` = any size has `stocks` with `qty > 0`. Store
   the `products[0]` dict in `raw`. Raise a clear `ValueError` if `products` is empty or the
   price object is missing (empty/blocked response), so the caller records a failed run
   rather than crashing.

3. **WbCollector** (`app/collectors/wb.py`): implements `MarketplaceCollector`
   (`marketplace = Marketplace.WB`). `collect()` builds the request from
   `region.geo["wb"]["dest"]` (the `dest` int seeded in Фаза 1) and `product.sku` (the WB
   `nm`): `GET https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest={dest}&spp=30&nm={nm}`,
   with the browser-like headers proven in the spike (`spike/check_price.py`: `User-Agent`
   Chrome, `Accept: */*`, `Accept-Language: ru-RU`, `Accept-Encoding: gzip, deflate` — **no
   brotli**, `Origin`/`Referer` wildberries.ru). Timeout from config. On non-200 or empty
   body raise `ValueError`. Delegate JSON → DTO to `parse_wb_card`. Endpoint base and timeout
   come from config (step 4), not hard-coded literals scattered around.

4. **Config** (`app/config.py`): add `home_region: str = "msk"`,
   `wb_card_url: str = "https://card.wb.ru/cards/v2/detail"`,
   `http_timeout_s: int = 30`. Keep the existing fields.

5. **Persistence + run wiring** (extend `app/repositories.py`): add minimal repos —
   `RunRepository` (`create(mode) -> Run` with `status=running`; `finish(run, status, stats)`
   setting `finished_at = now()`), and `PriceSnapshotRepository`
   (`add(product_id, region_id, run_id, obs: PriceObservation) -> PriceSnapshot`, insert-only).
   Reuse `AsyncSession` like the existing `ProductRepository`/`RegionRepository`. No queue
   logic.

6. **CLI** (`app/cli.py`): add subcommand `measure-wb` (argparse, matching the existing
   style). Flags: `--region CODE` (default `settings.home_region`), `--sku SKU` (optional —
   default: all active WB products). Flow: open a session; create a `Run(mode=manual)`;
   resolve the region by `code` and the target WB product(s); for each, run the (sync)
   collector via `asyncio.to_thread(collector.collect, product, region)`, then
   `PriceSnapshotRepository.add(...)`; count ok/failed; `RunRepository.finish(run, done,
   {"ok": …, "failed": …})`; commit. Print `run <id>: measured N, failed M`. A per-product
   failure (ValueError) is caught, counted as failed, and does not abort the run.

7. **Tests:**
   - `tests/fixtures/wb_card_sample.json` — a **realistic, hand-verified** `card.wb.ru` v2
     response (one product, one+ size with a price object in kopecks and stocks). Derive the
     shape from a real response; trim to what the parser reads. Committed so CI needs no
     network.
   - `tests/test_wb_parse.py` — unit tests for `parse_wb_card` against the fixture:
     correct `price`/`price_base` (kopecks→Decimal), `price_card is None`, `currency == "RUB"`,
     `is_available` true when stocked / false when all `qty == 0`, and `ValueError` on an
     empty-`products` payload. **No network, always runs in CI.**
   - Optional DB-backed test for `measure-wb` persistence may reuse the Фаза 1 pattern
     (`pytest.skip` when no DB reachable). Do not add a test that hits the live WB network in
     CI.

8. **Deps** (`pyproject.toml`): add `requests`; add `types-requests` to the dev/lint extra so
   `mypy` stays green. Update the lockfile if the project uses one.

## Constraints

- Model = Sonnet (pinned). Minimal read scope — the schema, enums, repos, config, db session
  and CLI are already on `main` (Фаза 1); build on them, don't rescan the repo. Reference
  `spike/check_price.py` only for the proven WB request shape (headers, endpoint, `dest`).
- `requests` for WB is deliberate (ADR-0005); do **not** introduce a browser or `curl_cffi`
  here. No proxy usage — direct connection only this phase.
- Money stays `Decimal`/`Numeric`; never float. WB kopecks → divide by 100.
- Secrets never committed; `.env` gitignored, only `.env.example` gets any new shape.
- Code/comments/commits in English; owner-facing docs (DEVLOG/BACKLOG) in Russian.
- Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy + pytest) exits green; `tests/test_wb_parse.py` runs (not
  skipped) and passes in CI with no network; DB-backed tests skip cleanly when no DB present;
  the Фаза 1 smoke/repo tests stay green.
- `parse_wb_card` correctly turns the committed sample into a `PriceObservation` (verified by
  the unit test), and raises on an empty/blocked response.
- Against a home-region network + local Postgres, `python -m app.cli measure-wb` creates a
  `run`, writes a real WB `price_snapshot` (sane non-zero price, `currency = RUB`), and prints
  the summary line. (Manual/local check — not part of the CI gate.)
- `docs/DEVLOG.md` updated with a pass entry; `BACKLOG.md` Фаза 2 item checked off.
- Merged into `main` via PR with the DoD gate green.
