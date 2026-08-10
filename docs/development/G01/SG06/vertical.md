# G01.SG06 — Complete Matrix Run, Persistence and Autonomous Operation

Parent Goal: G01 / Issue #30
Parent Subgoal: Issue #36
Planning branch: `brain/g01-regional-monitor-plan`
Status: PROPOSED / implementation blocked until SG06 vertical and whole-G01 semantic compilation PASS.

## Subgoal contract

### Purpose
Compose accepted SG01–SG05 interfaces into one operational primary run that plans the complete requested matrix before collection, preserves one accountable outcome for every planned unit, persists success and failure outcomes without semantic loss, and can run repeatedly/non-interactively without legacy city preparation.

### Inputs
- SG01 `ProductSet` and `CitySet`;
- SG02 city-bound `ProxyContext` authority + typed transport failures;
- SG03 typed WB per-product/per-city outcomes, including stock/availability and optional `wb_dest` semantics;
- SG04 typed Ozon per-product/per-city outcomes from the new autonomous proxy-first mechanism;
- SG05 explicit legacy fallback/support capability, which is not an implicit primary prerequisite;
- configured file and/or PostgreSQL output target.

### Output
One `RunPlan` and one completed `RunResultSet` for the exact planned semantic keys:

`(marketplace, product identifier, city)`

Every planned key has exactly one terminal success/failure outcome. Persisted minimum fields:
- `run_id`;
- timestamp;
- marketplace;
- product identifier;
- city;
- price (nullable on failure);
- status;
- error/error_code (nullable on success).

WB additionally preserves:
- stock quantity when evidenced/available;
- availability semantics.

The primary operational entrypoint is scheduler-ready: after data/configuration are supplied, invocation needs no `input()`, profile review/repair/add-region flow, manual city/PVZ selection, or legacy cookie preparation.

### Acceptance
1. Complete matrix is established before marketplace execution.
2. No planned key can silently disappear because a collector returns no row, raises, or returns malformed data.
3. Duplicate/unexpected/missing collector outcomes are detected explicitly rather than silently changing matrix cardinality.
4. One unit failure does not erase unrelated planned units.
5. File output persists the complete terminal RunResultSet, including failures.
6. PostgreSQL output persists the same semantic RunResultSet, including status/error/city and WB stock/availability.
7. File and PostgreSQL representations are semantically parity-checkable for one run.
8. `run_id` identifies one execution consistently across all rows/targets.
9. Primary non-interactive invocation can load configured product/city sources and output targets without prompts.
10. Repeated runs create independent run identity/timestamps and do not require manual regional setup.
11. SG05 fallback is never entered implicitly after a primary failure.
12. Browser/context resources created by SG04 are bounded/cleaned and never migrate between city identities.

### Failure conditions
- current-style `_enrich()` drops error rows;
- success-only persistence makes expected matrix count unverifiable;
- DB schema loses `city`, status/error, or WB stock semantics;
- persistence defaults a failed unit to a valid-looking availability/price;
- one collector exception aborts sibling units without terminal outcomes;
- primary runner uses legacy `config.regions`/profile/cookies as its required city source;
- scheduler invocation calls interactive `wizard_connect`, SKU/output menus, `review_profiles`, `repair_regions`, `add_new_regions` or other `input()` paths;
- a primary failure automatically enters SG05;
- run rows from different executions cannot be separated deterministically.

---

# PR01 — RunPlan expansion and exact outcome accounting

## Purpose
Create the matrix as an explicit contract before collection and reconcile all collector outcomes back to it.

### ST01 / T01 — Build deterministic RunPlan
Prompt: `prompts/work/G01-SG06/PR01-ST01-T01-C01-I01.md`

Input: accepted SG01 ProductSet + CitySet + enabled marketplaces.

Output:
- `run_id` allocated once for the execution;
- ordered/inspectable `RunPlan` of semantic keys `(marketplace, sku, city)`;
- deterministic expected count and per-marketplace counts;
- explicit handling of duplicate semantic input keys (no silent duplicate multiplication).

Acceptance:
- only products belonging to a marketplace produce units for that marketplace;
- every selected city participates for each selected product of enabled marketplace;
- plan creation performs no marketplace network calls;
- missing product/city inputs fail before execution with explicit input/plan error;
- no legacy profile/dest prerequisite is introduced.

### ST02 / T01 — Reconcile collector outcomes to RunPlan
Prompt: `prompts/work/G01-SG06/PR01-ST02-T01-C01-I01.md`

Input: immutable RunPlan + SG03/SG04 typed raw outcomes.

Output: one terminal accounted outcome per planned semantic key.

Rules:
- received typed outcome -> attach to exact planned key;
- no outcome for a planned key -> synthetic explicit `missing_outcome` failure for that key;
- multiple terminal outcomes for one key -> explicit duplicate/accounting failure, never arbitrary winner;
- unexpected key -> explicit orchestration/accounting finding and never silently appended as if planned.

Acceptance:
- `terminal_count == planned_count` after reconciliation;
- collector `[]`, exception or partial batch cannot shrink the result set;
- error preserves requested marketplace/SKU/city;
- reconciliation does not reinterpret marketplace price/stock semantics.

---

# PR02 — Canonical RunResult and lossless persistence

## Purpose
Normalize both marketplace outcome families into one persistence-safe row contract and make file/PostgreSQL store all terminal units.

### ST01 / T01 — Normalize typed marketplace outcomes into RunResult
Prompt: `prompts/work/G01-SG06/PR02-ST01-T01-C01-I01.md`

Input: reconciled planned outcomes from PR01 + accepted SG03/SG04 contracts.

Output: canonical `RunResult` row with stable common fields and nullable marketplace-specific fields.

Minimum fields:
`run_id`, `timestamp`, `marketplace`, `sku`, `city`, `price`, `status`, `error_code`, `error`, `source`.

WB-specific nullable fields:
`stock_qty`, `is_available`.

Useful already-existing price variants may be preserved as optional fields but are not allowed to replace the required common price/status contract.

Acceptance:
- failures keep identity and have nullable business values rather than invented zero/true defaults;
- zero stock is valid data distinct from failure;
- no proxy credentials, personalized SG05 cookies/tokens or other secrets enter rows;
- parser-specific raw exceptions are converted to safe diagnostic text/status before persistence.

### ST02 / T01 — Persist complete run to file
Prompt: `prompts/work/G01-SG06/PR02-ST02-T01-C01-I01.md`

Input: complete canonical RunResultSet.

Output: run-scoped file artifact(s) containing every terminal row.

Acceptance:
- failures are written, not filtered;
- same `run_id` and required common columns on every row;
- deterministic row count equals planned count;
- file target can be consumed without reconstructing missing combinations from logs;
- existing useful CSV behavior may be retained for compatibility, but canonical SG06 evidence has one complete run representation.

### ST03 / T01 — Migrate and persist complete run to PostgreSQL
Prompt: `prompts/work/G01-SG06/PR02-ST03-T01-C01-I01.md`

Input: complete canonical RunResultSet + existing `ParserDB`.

Output:
- idempotently migrated `parser_results` capable of storing the SG06 common fields and WB stock/availability;
- save method that writes every terminal row for one `run_id` transactionally at the run/batch boundary chosen by accepted implementation evidence.

Acceptance:
- schema includes unambiguous `city`, status/error and WB stock quantity/availability semantics;
- existing useful price columns remain compatible where possible;
- failure rows do not default `is_available=True`;
- all rows retain identical `run_id`;
- migration is idempotent for an existing database;
- DB errors are explicit and do not falsely report a fully persisted run.

---

# PR03 — Autonomous primary runner and repeated-run lifecycle

## Purpose
Execute the accepted RunPlan through SG02–SG04 without hidden legacy prerequisites and expose one non-interactive operational entrypoint suitable for external scheduling.

### ST01 / T01 — Compose collectors with per-unit failure isolation
Prompt: `prompts/work/G01-SG06/PR03-ST01-T01-C01-I01.md`

Input: RunPlan + CitySet + SG02 ProxyContext + SG03 WB collector + SG04 Ozon collector.

Output: raw typed outcomes delivered to PR01 reconciliation for every attempted unit/batch.

Acceptance:
- each city uses its own ProxyContext authority;
- WB may batch SKUs internally but terminal accounting remains per planned key;
- Ozon context/hidden browser, if used, remains city-bound;
- an exception in one city/marketplace/product is converted into failures for only the affected planned scope and execution continues where safe;
- no SG05 automatic fallback;
- no current `_enrich()`-style error filtering.

### ST02 / T01 — Provide non-interactive scheduler-ready primary invocation
Prompt: `prompts/work/G01-SG06/PR03-ST02-T01-C01-I01.md`

Input: configured source selections/paths or DB/env configuration + configured output target.

Output: one CLI/module entrypoint whose primary mode executes without interactive prompts.

Acceptance:
- products and cities can be selected from their accepted file/DB sources through arguments/config/env rather than `input()`;
- PG connection for primary may come from configured/env values rather than `wizard_connect()`;
- output file/PG/both selected non-interactively;
- no `review_profiles`, `repair_regions`, `add_new_regions`, manual `get_wb_dest`, legacy Ozon profile review/warm or other SG05 setup prerequisite;
- deterministic exit status distinguishes successful run completion from fatal configuration/persistence failure while unit-level marketplace failures remain in RunResultSet;
- external scheduler needs only launch the configured command/process; no scheduler service itself is required in G01.

### ST03 / T01 — Prove repeated-run lifecycle and resource isolation
Prompt: `prompts/work/G01-SG06/PR03-ST03-T01-C01-I01.md`

Input: accepted non-interactive runner and two sequential configured executions.

Output: repeat-run evidence.

Acceptance:
- each execution has distinct run_id and timestamps;
- same configured source data can run again without manual city interaction;
- no prior run result rows are mutated into the new run;
- SG04 HTTP/browser contexts are reused only where their own contract permits and never across wrong city identity;
- browser/driver/session resources are bounded and cleaned after their intended lifetime;
- expired/failed primary state produces typed failures rather than invoking SG05 automatically.

---

# PR04 — End-to-end SG06 acceptance and reverse assembly

## Purpose
Prove SG06 on deterministic mixed outcomes and then reverse-compose all SG06 children into the parent contract.

### ST01 / T01 — Prove complete mixed-outcome matrix and persistence parity
Prompt: `prompts/work/G01-SG06/PR04-ST01-T01-C01-I01.md`

Input: deterministic fixture with multiple cities, WB+Ozon products and a controlled mix of success/zero-stock/transport/context/parser failures.

Output: acceptance evidence showing:
- expected planned count;
- exact terminal count;
- unaffected siblings survive failures;
- file row set equals canonical RunResultSet;
- PostgreSQL row set equals canonical RunResultSet on required semantic fields;
- WB stock/availability and explicit failures survive both targets.

Acceptance: no success-only filtering and no silent cardinality drift.

### ST02 / T01 — Prove SG06 acceptance and reverse assembly
Prompt: `prompts/work/G01-SG06/PR04-ST02-T01-C01-I01.md`

Input: all accepted SG06 Task outputs/evidence.

Output: acceptance map and reverse composition:
`Prompt -> Task -> Stage -> Process -> SG06 -> G01 contribution`.

PASS requires:
- every Issue #36 acceptance clause has a producer and evidence;
- all SG01–SG05 interfaces consumed without semantic weakening;
- no SG05 implicit dependency reintroduced;
- no matrix/persistence/scheduler responsibility remains orphaned.

Fail-closed verdicts:
- `RUNPLAN_ACCOUNTING_INCOMPLETE`;
- `PERSISTENCE_SEMANTIC_LOSS`;
- `PRIMARY_NOT_NONINTERACTIVE`;
- `CROSS_SG_INTERFACE_MISMATCH`;
- `STRUCTURAL_REPAIR_REQUIRED`.

---

# Dependency graph

`SG01 ProductSet+CitySet -> PR01.ST01 RunPlan`

`SG02+SG03+SG04 + RunPlan -> PR03.ST01 execution -> PR01.ST02 reconciliation`

`reconciled outcomes -> PR02.ST01 RunResult -> PR02.ST02 file + PR02.ST03 PostgreSQL`

`PR03.ST02 non-interactive runner -> PR03.ST03 repeat lifecycle`

`PR01+PR02+PR03 -> PR04.ST01 integration proof -> PR04.ST02 SG06 closure`

SG05 is not an execution prerequisite. It remains an explicitly reachable reserve capability outside normal SG06 primary orchestration.

# Reverse composition target

- PR01 guarantees complete planned-unit cardinality and terminal accounting.
- PR02 guarantees no semantic loss between marketplace outcomes and durable outputs.
- PR03 guarantees real primary orchestration and scheduler-ready repeated lifecycle without human regional preparation.
- PR04 proves the composed behavior and closes SG06.

Their composition satisfies Issue #36 and contributes the final orchestration/persistence portions of G01.A01/A10/A11/A12 plus durable output requirements. Full G01 semantic compilation is performed separately after SG06 closes.