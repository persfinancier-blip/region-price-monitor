# G01.SG06 Semantic Compilation Report

Parent: Issue #36
Planning branch: `brain/g01-regional-monitor-plan`

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only)`

This is a planning/virtual-execution verdict. It proves the proposed Prompt -> Task -> Stage -> Process -> SG06 structure is compositionally sufficient and compatible with active SG01–SG05 contracts. It does not claim implementation or live PostgreSQL/marketplace acceptance has already run.

## Current-runtime findings used by virtual execution

1. `parser/core/collect.py::_enrich()` currently discards every result containing `error`; therefore current terminal row count cannot represent the requested matrix.
2. `collect.py` builds output from whatever success rows collectors happened to return rather than from an explicit precomputed RunPlan.
3. Current Ozon collection still depends on legacy `cookies.json` and current WB branch skips cities without `wb_dest`; accepted SG03/SG04 replace these primary semantics before/while SG06 composes them.
4. Current `storage.save_csv()` writes only the supplied non-empty result list and therefore cannot prove missing planned units unless SG06 supplies a complete canonical RunResultSet.
5. Current PostgreSQL `parser_results` lacks required SG06 `status`, `error`, canonical city and WB `stock_qty` semantics.
6. Current `ParserDB.save_results()` defaults `is_available` to `True` when absent; this can turn unknown/failure into valid-looking availability and must not survive SG06 canonical persistence.
7. Current desktop CLI uses interactive product/output menus, `wizard_connect`, profile review/repair and add-region workflows; these cannot be the scheduler-ready primary entrypoint.
8. Current `collect.py` is nominally non-interactive, but its city source remains legacy `config.regions` and its Ozon path requires legacy authenticated cookies; it is therefore not the final SG01–SG05-composed primary runner.

## Virtual Prompt execution

### PR01.ST01.T01 — Build deterministic RunPlan
Virtual result: PASS.

An explicit semantic key `(marketplace, sku, city)` and run_id can be created from SG01 ProductSet/CitySet before any network request. This removes current collector-return cardinality as semantic authority. Duplicate semantic input handling is explicit/tested rather than silently multiplying rows.

### PR01.ST02.T01 — Reconcile outcomes to RunPlan
Virtual result: PASS.

Accepted SG03/SG04 outcomes already retain requested identity and typed failures. Therefore reconciliation can produce exactly one terminal row per planned key, synthesize `missing_outcome` for absent collector rows, reject duplicate/unexpected keys, and preserve marketplace semantics unchanged.

This directly closes the current `_enrich()`/partial-batch loss mode.

### PR02.ST01.T01 — Canonical RunResult
Virtual result: PASS.

SG03 supplies price + stock/availability + typed failures; SG04 supplies price + typed failures. These can normalize into one common row with nullable business values and WB-specific stock fields. No parent requirement forces fake zero/true defaults.

### PR02.ST02.T01 — Complete file persistence
Virtual result: PASS.

Existing CSV infrastructure is sufficient as a base, but the canonical writer must receive the complete RunResultSet rather than success subsets. A run-level artifact gives direct matrix cardinality evidence while legacy per-region files may remain optional compatibility output.

### PR02.ST03.T01 — PostgreSQL persistence
Virtual result: PASS.

Existing ParserDB already owns idempotent schema creation/migration and run_id-based result persistence. The required extension is structurally local: add city/status/error/stock semantics, preserve useful existing price fields, remove `is_available=True` failure default, and write all terminal rows. No new database subsystem is required.

Live disposable-PostgreSQL acceptance remains execution evidence; the semantic model does not fake that runtime proof.

### PR03.ST01.T01 — Collector orchestration
Virtual result: PASS.

RunPlan + CitySet + SG02 ProxyContext can call SG03 and SG04 interfaces without reintroducing legacy region authority. WB batching is compatible if per-key outcomes remain reconstructable. Ozon hidden browser remains SG04-owned and city-bound. Narrow exception isolation plus PR01 reconciliation guarantees sibling accounting.

### PR03.ST02.T01 — Non-interactive scheduler-ready entrypoint
Virtual result: PASS.

SG01 source adapters plus existing env support make a no-stdin entrypoint possible without creating a scheduler service. This Task only needs to select accepted product/city sources/output targets through arguments/config/env and bypass existing interactive desktop functions. Existing interactive CLI can remain separately available.

### PR03.ST03.T01 — Repeated-run lifecycle
Virtual result: PASS.

One run_id per RunPlan plus run-scoped persistence permits two independent executions. SG04 already owns bounded context/browser lifecycle and city binding; SG06 only verifies correct orchestration lifetime and no cross-run/cross-city misuse. No manual regional maintenance is required by the composed primary path.

### PR04.ST01.T01 — Mixed matrix + persistence parity
Virtual result: PASS as a deterministic acceptance design.

A fixture with two cities, WB/Ozon products, positive stock, zero stock and controlled failures can deterministically prove planned count == terminal count and compare file/PG semantic rows to canonical RunResultSet. If PostgreSQL execution is unavailable, the Task must report the missing live DB evidence rather than claim runtime acceptance.

### PR04.ST02.T01 — SG06 closure
Virtual result: PASS.

Every Issue #36 acceptance clause has one or more exact producing Tasks; no SG05 fallback output is needed by primary execution; no child Task owns marketplace semantics already assigned to SG03/SG04.

## Reverse assembly

### Prompt -> Task
All ten active SG06 C01.I01 Prompts are one-to-one with bounded Tasks and have explicit input/output/acceptance/evidence/failure boundaries.

PASS.

### Task -> Stage -> Process
- PR01: complete pre-execution plan + terminal reconciliation.
- PR02: canonical row + file persistence + PostgreSQL persistence.
- PR03: primary execution + non-interactive invocation + repeated-run lifecycle.
- PR04: mixed end-to-end proof + SG06 closure.

No Stage has an uncovered responsibility.

PASS.

### Process -> SG06
Issue #36 coverage:
- full matrix accounting -> PR01 + PR04;
- unit failure isolation -> PR01.ST02 + PR03.ST01 + PR04.ST01;
- every planned unit success/error -> PR01;
- file output -> PR02.ST02 + PR04.ST01;
- PostgreSQL output -> PR02.ST03 + PR04.ST01;
- city/product identity -> PR01 + PR02;
- WB stock persists -> PR02 + PR04;
- repeated run no manual city interaction -> PR03.ST03;
- scheduler-ready invocation -> PR03.ST02.

PASS.

## Cross-SG interface compilation

### SG01 -> SG06
PASS. ProductSet/CitySet are direct RunPlan inputs. SG06 does not route primary CitySet through legacy `review_profiles`/`repair_regions`/`add_new_regions`.

### SG02 -> SG06
PASS. CityRecord produces/reuses the shared ProxyContext. Typed proxy/transport failures can survive into RunResult rather than being converted to empty data.

### SG03 -> SG06
PASS conditional on SG03 execution-time stock evidence. SG03's normalized WB output includes optional-dest semantics, stock/availability and typed failure; SG06 preserves rather than reinterprets them.

### SG04 C02 -> SG06
PASS conditional on SG04 runtime engine/context evidence. SG04 new proxy-first outcomes can be orchestrated/persisted without requiring SG05 personalized authenticated cookies. Hidden Selenium, if selected by SG04 evidence, remains city-bound and zero-human.

### SG05 C02 -> SG06
PASS. SG05 is an explicitly reachable reserve/support capability, not a primary input prerequisite. SG06 does not auto-enter it after failure. Preservation of personalized authenticated cookies remains isolated in fallback.

## Lifecycle / authority checks

- RunPlan authority exists before collectors and survives until reconciliation/persistence.
- SG02 ProxyContext authority remains city-bound for the network lifetime; SG06 does not create raw competing proxy authority.
- SG03/SG04 semantic outcomes remain authoritative for marketplace meaning; SG06 only accounts/normalizes common persistence fields.
- SG04 browser/session resources retain SG04 lifecycle rules; SG06 verifies cleanup/repeat isolation but does not keep them alive across wrong cities.
- SG05 credential/profile lifetime is not pulled into primary lifecycle.
- run_id remains alive through file/PG persistence and uniquely separates repeated executions.

PASS.

## Minimality check

Ten Tasks are minimum sufficient for the accepted responsibility boundaries:
- plan creation must be separate from reconciliation so expected cardinality cannot be derived from returned rows;
- RunResult normalization must precede both storage implementations;
- file and PostgreSQL persistence have different schemas/failure modes and should not share one Task;
- execution, invocation configuration and repeated-run lifecycle are distinct;
- mixed acceptance fixture and closure gate are separate so closure cannot modify implementation to manufacture PASS.

No separate scheduler service, fallback policy, marketplace parser or provider-management Task is required by SG06.

## SG06 final vertical verdict

`SEMANTIC_COMPILE_PASS (vertical only)`.

Next gate after durable Issue/Prompt materialization is the separate whole-contour reverse semantic compilation of active SG01–SG06 generations into G01.