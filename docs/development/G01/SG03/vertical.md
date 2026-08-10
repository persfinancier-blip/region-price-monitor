# G01.SG03 — Wildberries Regional Price and Stock

Parent Goal: G01 / Issue #30
Parent Subgoal Issue: #33
Status: PROPOSED vertical generation; implementation blocked pending full G01 semantic compilation.

## Subgoal contract

### Purpose
For every requested WB `product × city`, use the SG02 city-bound proxy transport to obtain a regional WB response and produce a typed WB observation containing regional price plus endpoint-proven stock/availability. `wb_dest` is optional: when present it is sent; when absent the request is made without a forced `dest` parameter. Transport/request/parser failures must never be represented as zero stock or a valid empty observation.

### Inputs
- WB subset of SG01 `ProductSet`.
- SG01 `CityRecord`: `city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`.
- accepted SG02 `ProxyContext` / requests transport boundary.
- current WB consumer endpoint configured by the product.

### Outputs
For each requested WB `sku × city`, one typed outcome carrying at minimum:
- marketplace=`wb`;
- sku;
- city;
- price / price_base when present;
- `stock_qty` or another explicitly evidenced stock quantity field;
- `is_available` derived from evidenced stock semantics, not from price;
- success / typed semantic failure / typed transport failure;
- enough endpoint-context metadata to prove whether `wb_dest` was forced or omitted, without leaking proxy credentials.

Exact stock field path and aggregation rule MUST be established from current endpoint evidence before parser implementation. No guessed schema is authority.

## Process decomposition

### G01.SG03.PR01 — WB endpoint evidence and stock semantics
Purpose: turn the undocumented current `card.wb.ru/cards/v4/detail` response into a durable tested contract before parsing stock.

#### ST01 — Current endpoint evidence capture
##### T01 — Capture and classify current WB price/stock response shapes
Input: current WB endpoint, representative WB SKUs, SG02 transport, at least one city/proxy context, with and without `wb_dest` where runtime access allows.
Output: sanitized fixtures/evidence for: product with positive stock, product/variant with zero stock or unavailable state, malformed/not-found semantic case, request with `wb_dest`, request without forced `dest`. Record exact response paths that carry price and stock/availability.
Acceptance: evidence is current, sanitized, reproducible enough for parser tests, and does not infer stock from price. If current endpoint does not expose a trustworthy regional stock quantity/availability signal, emit `WB_STOCK_CONTRACT_UNPROVEN` and stop SG03 for model amendment rather than inventing a field.

#### ST02 — Stock normalization contract
##### T01 — Define WBObservation stock and availability semantics from evidence
Input: accepted ST01 fixtures/schema.
Output: one explicit normalization rule for price, `stock_qty`, `is_available`, multi-size/multi-stock aggregation if present, zero stock, missing product, missing size, malformed response.
Acceptance: every normalized field is traceable to fixture evidence; `is_available` is not `price > 0`; zero stock is a valid semantic result and remains distinct from transport/parser failure.

### G01.SG03.PR02 — Optional-dest WB request construction
Purpose: create WB request semantics compatible with the Goal's optional `wb_dest` rule and SG02 proxy-first transport.

#### ST01 — WB request builder and transport handoff
##### T01 — Build WB detail requests with optional `wb_dest`
Input: WB SKU batch, CityRecord, accepted SG02 ProxyContext/requests adapter.
Output: request specification/call path where `dest` is included only when `wb_dest` is non-empty; otherwise the `dest` parameter is omitted entirely. Every primary request uses the supplied ProxyContext.
Acceptance: both with-dest and no-dest paths are valid construction paths; no placeholder/zero/empty `dest` is forced; no silent direct-network fallback; HTTP/transport failure remains typed from SG02.
Failure: missing `wb_dest` aborts or triggers browser/manual setup; raw city proxy string bypasses SG02.

### G01.SG03.PR03 — WB price and stock parser
Purpose: parse one current WB response contract into explicit product observations without losing semantic distinctions.

#### ST01 — Price + stock extraction
##### T01 — Parse evidenced WB price and stock fields
Input: accepted PR01 fixtures and normalization contract.
Output: parser that returns per-product normalized price fields plus stock quantity/availability using only evidenced response paths/aggregation.
Acceptance: positive stock, zero stock, multiple sizes/stocks (if present), and price-only edge cases follow the accepted contract; product identity preserved; stock never inferred from price.

#### ST02 — WB semantic outcome classification
##### T01 — Distinguish zero stock, not-found, malformed and transport failure
Input: parser result + SG02 TransportOutcome.
Output: typed WB outcomes such that `stock_qty=0` is valid data, while missing product, malformed response, HTTP failure, timeout, proxy/auth failure and unexpected parser failure remain explicit non-success states.
Acceptance: no `[]`/missing row is used as a universal failure signal; batch members can be accounted individually; secret-free diagnostics.

### G01.SG03.PR04 — WB collector integration and SG03 closure
Purpose: bind SG01 city/product inputs + SG02 transport + SG03 request/parser into the actual WB collector boundary without taking persistence/scheduler responsibility from SG06.

#### ST01 — Product × city WB observation handoff
##### T01 — Integrate WB collector for both optional-dest paths
Input: WB ProductSet subset, CitySet, accepted PR02 request path, PR03 outcome parser.
Output: for each requested WB SKU/city, one typed WB observation/outcome containing city identity, price, stock/availability and status/error. The collector must not skip an entire city merely because `wb_dest` is absent.
Acceptance: city proxy used; with-dest and no-dest paths exercised; one SKU failure does not erase successful sibling observations; no legacy `get_wb_dest` prerequisite.
Boundary: persistence schema/write is SG06; legacy browser fallback is SG05.

#### ST02 — SG03 acceptance and reverse-assembly gate
##### T01 — Prove WB regional price + stock contract
Input: all SG03 task outputs/evidence.
Output: deterministic acceptance map for Issue #33 and reverse composition report through SG03 contribution to G01.
Acceptance evidence must prove:
1. regional WB price path exists;
2. stock/availability comes from current endpoint evidence;
3. `stock_qty=0` / unavailable is distinct from failure;
4. `wb_dest` present path works;
5. `wb_dest` absent path is accepted and request omits forced dest;
6. SG02 ProxyContext is used on both paths;
7. no stock-from-price inference;
8. no manual WB city selection is required in the primary path;
9. SG03 output is sufficient for SG06 persistence without SG03 implementing persistence itself.

## Dependency graph
`PR01.ST01.T01 -> PR01.ST02.T01 -> PR03.ST01.T01 -> PR03.ST02.T01`

`SG02 + CityRecord -> PR02.ST01.T01`

`PR02.ST01.T01 + PR03.ST02.T01 -> PR04.ST01.T01 -> PR04.ST02.T01`

PR01 evidence capture may use a narrow runtime probe. Runtime inability to reach the endpoint is not permission to guess response fields; it yields a typed evidence blocker.

## Reverse composition
- PR01 proves what WB stock actually means in the endpoint response.
- PR02 proves optional-dest + proxy-first request semantics.
- PR03 turns response/transport into correct price+stock outcomes.
- PR04 binds those outputs to every WB product×city unit.

Their composition satisfies Issue #33 without absorbing Ozon, legacy fallback, persistence or scheduling.

## Automatic vertical FAIL
- endpoint stock field/aggregation is guessed rather than evidenced;
- `is_available` remains based on price;
- absent `wb_dest` still skips WB;
- zero stock can be confused with request failure;
- SG02 ProxyContext can be bypassed;
- collector drops failed requested units without an explicit outcome;
- SG03 expands into Ozon, fallback, DB/result persistence or scheduler work.
