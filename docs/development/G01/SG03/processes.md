# G01.SG03 process contracts

Parent: Issue #33
Canonical vertical: `docs/development/G01/SG03/vertical.md`

## PR01 — WB endpoint evidence and stock semantics
Input: current WB endpoint access, representative WB SKUs, SG02 transport.
Output: sanitized current-response fixtures/schema + explicit WB stock normalization contract.
Acceptance: positive-stock and zero/unavailable semantics evidenced; no stock-from-price inference; unknown schema fails closed as `WB_STOCK_CONTRACT_UNPROVEN`.
Evidence: captured/sanitized response fixtures and schema-to-normalization map.
Failure: guessed response field or aggregation rule.

## PR02 — Optional-dest WB request construction
Input: WB SKU batch + CityRecord + SG02 ProxyContext.
Output: request path where `dest` is present only when `wb_dest` is present; otherwise omitted; all primary traffic uses SG02.
Acceptance: with/without-dest request construction, no direct fallback, typed SG02 failures.
Evidence: request-spy tests for params and ProxyContext.
Failure: missing dest blocks WB or triggers manual browser setup.

## PR03 — WB price and stock parser
Input: accepted PR01 response contract + SG02 transport outcome.
Output: per-product WB semantic outcome containing price and endpoint-evidenced stock/availability or explicit typed failure.
Acceptance: zero stock, not-found, malformed and transport failures remain distinct; batch identity preserved.
Evidence: fixture parser tests and failure-classification tests.
Failure: `[]` or missing row becomes universal failure representation; price used as stock proxy.

## PR04 — WB collector integration and SG03 closure
Input: SG01 WB products/cities + PR02 request + PR03 parser.
Output: one typed WB outcome for every requested `sku × city`, with price + stock/availability or explicit failure, ready for SG06 persistence.
Acceptance: proxy-first both dest paths, no city skip when dest absent, no manual `get_wb_dest`, complete Issue #33 evidence map.
Evidence: collector integration fixtures/spies + reverse-assembly report.
Failure: SG03 absorbs persistence/scheduler/fallback/Ozon work or loses requested units.
