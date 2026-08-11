# G01.SG03 vertical semantic compile report

Subgoal: Issue #33 — Wildberries Regional Price and Stock
Branch: `brain/g01-regional-monitor-plan`
Verdict: **SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_PROBE_REQUIRED)**
Implementation authorization: **NO** — global G01 compilation remains incomplete.

## Baseline facts compiled from current repository
1. `parser/core/wb.py` currently requires `dest`, always sends it, accepts only a raw proxy string, parses price from the first size, sets `is_available = price > 0`, and converts broad HTTP/exception failures to `[]`.
2. `parser/core/collect.py` currently skips WB entirely when a region lacks `wb_dest`.
3. Current primary collector therefore violates SG03 before any new code: optional dest is not honored, stock is not parsed, price is incorrectly used as availability proxy, and requested-unit failures may disappear.
4. SG02 is the planned authority for authenticated city ProxyContext and typed transport failures; SG03 must consume it rather than recreate proxy handling.

## External/current evidence boundary
The product uses the consumer endpoint `card.wb.ru/cards/v4/detail`, which is not treated as a stable documented Seller API contract in this model. Therefore its stock JSON path/aggregation cannot be asserted from memory. The first SG03 Task is an evidence gate that captures current sanitized response fixtures. If it cannot prove a trustworthy stock/availability signal, SG03 stops with `WB_STOCK_CONTRACT_UNPROVEN`.

This is compatible with the general WB data model where stock quantity is a distinct inventory datum rather than a price-derived property; however SG03 requires evidence from the actual endpoint used by the parser before binding a concrete stock path.

## Proposed vertical
### PR01 — Endpoint evidence and stock semantics
- ST01.T01: capture current sanitized response shapes.
- ST02.T01: define exact stock/availability normalization from those fixtures.

### PR02 — Optional-dest request construction
- ST01.T01: include `dest` only when `wb_dest` exists; otherwise omit it; always use SG02 ProxyContext.

### PR03 — Price and stock parser
- ST01.T01: parse evidenced price+stock fields.
- ST02.T01: classify zero stock / not-found / malformed / transport failure per requested SKU.

### PR04 — Collector integration and closure
- ST01.T01: produce one typed WB outcome for every requested `sku × city`, including no-dest cities.
- ST02.T01: SG03 acceptance/reverse-assembly gate.

## Virtual Prompt execution

### T1 — endpoint evidence capture
Expected result A: sanitized fixtures prove exact price path plus one or more stock/availability fields for the regional request context, including enough structure to distinguish positive and zero/unavailable semantics. Output can feed T2.

Expected result B: endpoint access or schema cannot prove required stock semantics. Output is `WB_STOCK_CONTRACT_UNPROVEN`; T2/T4/T5/T6/T7 cannot honestly close. No guessed schema is produced.

Result: **model safe in both branches**.

### T2 — stock normalization contract
Given T1 result A, derives one deterministic rule for stock quantity/availability, including any required multi-size/multi-stock aggregation. Zero stock is valid data. `is_available` no longer depends on price.

Result: **PASS conditional on accepted T1 evidence**.

### T3 — optional-dest request path
Replaces mandatory-dest construction with: `wb_dest != None -> dest=<value>`; `wb_dest == None -> omit dest`. Both forms consume SG02 ProxyContext and typed TransportOutcome.

Result: **PASS**. Independent of stock JSON details.

### T4 — price+stock parser
Consumes only accepted T2 fixture contract; produces normalized per-product semantic data. Does no networking.

Result: **PASS conditional on T2**.

### T5 — semantic outcome classification
Accounts every requested SKU and keeps valid zero stock separate from missing product, malformed body and SG02 transport errors. Eliminates primary-path `[]` ambiguity.

Result: **PASS conditional on T4 + SG02**.

### T6 — collector integration
For every WB city, runs regardless of whether `wb_dest` exists; preserves city/SKU identity; uses SG02 ProxyContext; hands off typed success/failure outcomes. Does not persist stock itself.

Result: **PASS conditional on T3 + T5**.

### T7 — closure
Maps evidence to Issue #33 and checks reverse composition through G01.

Result: **PASS as semantic model**; runtime stock evidence remains a point-of-use prerequisite before downstream stock implementation/acceptance.

## Reverse assembly

### Prompt -> Task
Each Prompt has one bounded Task result. No Prompt expands into Ozon, persistence, scheduler or legacy-fallback ownership.

### Task -> Stage -> Process
- PR01 output: evidenced stock contract.
- PR02 output: optional-dest proxy-first request path.
- PR03 output: typed per-SKU price+stock outcomes.
- PR04 output: actual product×city WB collector handoff + acceptance evidence.

### Processes -> SG03
Composition yields exactly Issue #33 output: for each requested WB product/city, regional price plus endpoint-evidenced stock/availability or explicit typed failure, with optional `wb_dest` and city ProxyContext.

### SG03 -> G01 contribution
- A05 WB regional price: covered by PR03/PR04.
- A06 WB regional stock: covered by PR01/PR03/PR04, guarded by runtime evidence.
- A08 optional WB dest: covered by PR02/PR04.
- A10 failure isolation: covered by PR03/PR04.
- A12 complete matrix contribution: SG03 produces account-able WB unit outcomes for SG06; SG06 owns whole-system matrix closure.
- A01/A11 autonomy contribution: primary WB path does not invoke manual `get_wb_dest` when dest is absent.

No G01 requirement is falsely claimed outside SG03's contribution.

## Interface/lifetime checks
- SG01 CityRecord lifetime: available before PR02/PR04; optional dest remains optional.
- SG02 ProxyContext lifetime: must cover each WB request; SG03 does not terminate or bypass it.
- T1 current-endpoint evidence is a prerequisite for T2/T4/T5 stock semantics; advance Prompt existence does not imply execution readiness.
- SG06 may persist SG03 normalized fields later; SG03 output contract provides `stock_qty`/availability/status without prescribing persistence schema.

## Key compile findings
1. Current `is_available = price > 0` must be removed from primary WB semantics.
2. Current collector's `if products.get("wb") and dest` condition must not survive the primary path.
3. Current `[]` error collapse is incompatible with zero-stock/failure separation and complete unit accounting.
4. Stock extraction must inspect all evidenced relevant size/stock entries; current `sizes[0]` assumption cannot be extended to stock without evidence.
5. Live endpoint schema is a runtime-only fact; the model correctly blocks on unproven schema rather than widening user inputs or guessing.

## Final vertical verdict
**SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_PROBE_REQUIRED).**

This verdict means the SG03 hierarchy/contracts/Prompts compose correctly and fail closed around the unresolved current endpoint stock schema. It does NOT claim that live WB stock extraction has already been proven, and it does NOT authorize implementation before the remaining SG04–SG06 verticals and full G01 reverse compilation pass.
