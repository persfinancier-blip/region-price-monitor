# G01.SG01 — Dynamic Products and Cities Input — vertical decomposition

Parent Goal: #30 / `docs/development/G01/goal.md`  
Parent Subgoal: #31 / `docs/development/G01/subgoals.md`

Status: **PROPOSED / DEVELOPMENT BLOCKED** until this vertical compiles and the whole G01 contour later compiles.

## SG01 contract

### Purpose
Provide normalized dynamic `ProductSet` and `CitySet` inputs from file or PostgreSQL without operational product/city/proxy values being hardcoded in source code.

### Input
- product source = file or PostgreSQL;
- city source = file or PostgreSQL;
- city raw record minimum fields:
  - `city` required;
  - `proxy` required;
  - `proxy_user` required;
  - `proxy_password` required;
  - `wb_dest` optional.

### Output
- canonical `ProductSet` compatible with the existing parser: marketplace-separated SKU collections for WB/Ozon;
- canonical `CitySet`: normalized city records containing only the required proxy connection fields plus optional `wb_dest`;
- downstream code can consume either set without knowing whether it came from file or PostgreSQL.

### SG01 acceptance
1. Product file source works.
2. Product PostgreSQL source works.
3. City file source works.
4. City PostgreSQL source works.
5. Equivalent file/DB data produce equivalent normalized sets.
6. Missing required city proxy fields fail explicitly.
7. Missing/blank `wb_dest` is valid and normalizes to no forced destination.
8. Adding/changing a product or city requires data change only, not source-code editing.
9. No additional mandatory city field is introduced.

---

# PR01 — Product source preservation and normalization

## Contribution to SG01
Preserve the already working dynamic product acquisition and establish its normalized boundary so later integration does not regress it while city input is added.

## Input contract
One selected existing product source:
- CSV/Excel product file (`marketplace`, `sku`);
- PostgreSQL `parser_skus`;
- existing `products.json` compatibility path may remain as a local cached/file path.

## Output contract
`ProductSet = {"wb": [sku...], "ozon": [sku...]}` with marketplace values validated and SKUs represented consistently as strings.

## PR01 acceptance
- existing file and DB product paths remain usable;
- invalid/unsupported records do not silently become valid products;
- normalized file and DB fixtures representing the same products compare equal;
- no product values are hardcoded into implementation.

## Evidence
Unit/contract tests for file and DB normalization plus regression of current supported file path.

## Failure conditions
Product loading is broken, one required source disappears, or downstream receives source-specific structures.

## ST01 — Product normalized-source boundary

### Output
A tested product-source boundary returning one canonical `ProductSet` regardless of file/DB origin.

### T01 — Normalize and preserve product sources
Identity: `G01.SG01.PR01.ST01.T01`

**Input:** current `cli.py`, `db.py`, `config.py`, product fixtures.  
**Output:** minimal refactor/adapter + tests proving product source parity.  
**Allowed write scope:** `parser/core/cli.py`, `parser/core/db.py`, `parser/core/config.py`, optional new `parser/core/input_models.py` / `parser/core/product_sources.py`, product-source tests/fixtures only.  
**Dependencies:** none inside SG01.  
**Prompt:** `prompts/work/G01-SG01/PR01-ST01-T01-C01-I01.md`.

---

# PR02 — City source acquisition and normalization

## Contribution to SG01
Introduce city input as a first-class dynamic source with the exact minimum user contract agreed for G01.

## Input contract
Raw city rows from file or PostgreSQL.

## Output contract
`CitySet` of normalized records:

```text
city             required non-empty
proxy            required non-empty
proxy_user       required non-empty
proxy_password   required non-empty
wb_dest          optional; blank/missing => None
```

No other user-supplied field is mandatory.

## PR02 acceptance
- file and PostgreSQL supported;
- same raw semantic city data normalize identically;
- required-field errors are explicit and identify the row/city when possible;
- absent `wb_dest` remains valid;
- city/proxy values are data, not source-code constants.

## Evidence
Validation tests, file loader tests, DB loader tests, parity fixture.

## Failure conditions
Any required source is missing, `wb_dest` becomes mandatory, proxy credentials are inferred/hardcoded, or source-specific structures leak downstream.

## ST01 — Canonical CityRecord and validation

### T01 — Define minimum CityRecord normalization
Identity: `G01.SG01.PR02.ST01.T01`

**Input:** SG01 city contract.  
**Output:** one minimal validation/normalization function/model for the five agreed fields.  
**Allowed write scope:** optional new `parser/core/input_models.py` and city-contract tests only.  
**Dependencies:** none.  
**Prompt:** `prompts/work/G01-SG01/PR02-ST01-T01-C01-I01.md`.

## ST02 — City file source

### T01 — Load cities from file
Identity: `G01.SG01.PR02.ST02.T01`

**Input:** city CSV/Excel rows + canonical CityRecord normalizer from PR02.ST01.T01.  
**Output:** file loader returning canonical `CitySet`; sample fixture/file using only the five-field contract.  
**Allowed write scope:** `parser/core/config.py`, optional `parser/core/city_sources.py`, parser-visible sample city file if needed, city-file tests/fixtures.  
**Dependencies:** PR02.ST01.T01 contract.  
**Prompt:** `prompts/work/G01-SG01/PR02-ST02-T01-C01-I01.md`.

## ST03 — City PostgreSQL source

### T01 — Load cities from PostgreSQL
Identity: `G01.SG01.PR02.ST03.T01`

**Input:** PostgreSQL connection + canonical CityRecord normalizer.  
**Output:** minimal `parser_cities` persistence/read path returning canonical `CitySet`. Schema contains the agreed data fields; implementation-generated DB mechanics (indexes/constraints) may exist but must not create new required user input.  
**Allowed write scope:** `parser/core/db.py`, optional `parser/core/city_sources.py`, city-DB tests/fixtures.  
**Dependencies:** PR02.ST01.T01 contract.  
**Prompt:** `prompts/work/G01-SG01/PR02-ST03-T01-C01-I01.md`.

---

# PR03 — Source-neutral input handoff and SG01 closure

## Contribution to SG01
Compose product and city source outputs into a stable downstream boundary and prove the user can change data without editing parser code.

## Input contract
- canonical ProductSet from PR01;
- canonical CitySet from PR02;
- source selection/configuration required to choose file or PostgreSQL.

## Output contract
A source-neutral input handoff usable by later SG02/SG03/SG04/SG06 logic:

```text
Inputs {
  products: ProductSet,
  cities: CitySet
}
```

Neither downstream consumer nor normalized object identity depends on source origin.

## PR03 acceptance
- all four required combinations are representable: product file/DB × city file/DB;
- file/DB semantic parity is tested;
- adding/changing product/city is data-only;
- no city field beyond the agreed five becomes mandatory;
- product loading regression remains green.

## Evidence
Cross-source integration tests and explicit SG01 contract matrix.

## Failure conditions
Downstream must branch on file-vs-DB shape, source choice changes semantics, or user must edit code to add cities/products.

## ST01 — Unified input composition

### T01 — Compose normalized product and city inputs
Identity: `G01.SG01.PR03.ST01.T01`

**Input:** PR01 ProductSet + PR02 CitySet source adapters.  
**Output:** one minimal source-neutral loading/orchestration boundary; existing interactive CLI may call it, while non-interactive scheduler UX remains SG06 scope.  
**Allowed write scope:** `parser/core/cli.py`, optional `parser/core/inputs.py`, source integration tests.  
**Dependencies:** PR01.ST01.T01 + PR02.ST02.T01 + PR02.ST03.T01.  
**Prompt:** `prompts/work/G01-SG01/PR03-ST01-T01-C01-I01.md`.

## ST02 — Contract parity and minimality gate

### T01 — Prove SG01 source parity and minimum contract
Identity: `G01.SG01.PR03.ST02.T01`

**Input:** implemented PR01/PR02/PR03.ST01 boundaries and fixtures.  
**Output:** deterministic tests/evidence proving SG01 acceptance items 1–9 and detecting regression to hardcoded cities or mandatory `wb_dest`.  
**Allowed write scope:** SG01 tests/fixtures and minimal correction inside files already authorized by SG01 Tasks if a test exposes a contract mismatch; no proxy transport/collector work.  
**Dependencies:** all prior SG01 Tasks.  
**Prompt:** `prompts/work/G01-SG01/PR03-ST02-T01-C01-I01.md`.

---

# Dependency / lifecycle graph

```text
PR01.ST01.T01 ------------------------------┐
                                           │
PR02.ST01.T01 -> PR02.ST02.T01 ------------┼-> PR03.ST01.T01 -> PR03.ST02.T01
              -> PR02.ST03.T01 ------------┘
```

Parallelism is contract-first: PR01 product work can proceed independently of PR02 city work. PR02 file and DB adapters may be implemented after the shared CityRecord contract exists. PR03 requires both complete source families.

No Task in SG01 owns proxy network transport, WB/Ozon HTTP behavior, stock extraction, legacy fallback behavior, scheduler operation, or result persistence.

---

# Reverse contract compilation

## Task -> Stage
- PR01.ST01.T01 returns the complete ST01 product normalized-source boundary.
- PR02.ST01.T01 returns canonical CityRecord validation required by both city source adapters.
- PR02.ST02.T01 returns the complete city file-source Stage.
- PR02.ST03.T01 returns the complete city PostgreSQL Stage.
- PR03.ST01.T01 returns unified ProductSet + CitySet handoff.
- PR03.ST02.T01 returns explicit proof/minimality closure for SG01.

Result: **Task -> Stage composition PASS** on the proposed contracts.

## Stage -> Process
- PR01.ST01 provides all PR01 outputs: preserved file/DB product acquisition and canonical ProductSet.
- PR02.ST01 + ST02 + ST03 jointly provide canonical validation + file + DB acquisition = complete CitySet responsibility.
- PR03.ST01 + ST02 provide source-neutral integration plus proof that source choice does not leak downstream.

Result: **Stage -> Process composition PASS**.

## Process -> SG01
- PR01 supplies dynamic normalized products.
- PR02 supplies dynamic normalized cities under the minimum five-field contract.
- PR03 composes them and proves parity/minimality/no-hardcode behavior.

All SG01 acceptance items 1–9 have exactly one producing responsibility and at least one evidence owner.

Result: **Process -> SG01 composition PASS**.

## SG01 -> G01 contribution check
SG01 directly supplies G01 requirements:
- G01.A02 dynamic products;
- G01.A03 dynamic cities;
- G01.A04 minimum proxy-city input contract at the data layer;
- G01.A08 optional `wb_dest` accepted at input;
- the input half of G01.A12 complete matrix planning (`ProductSet × CitySet`).

SG01 intentionally does **not** claim the network/runtime half of A04/A08/A12; those remain SG02/SG03/SG06 responsibilities already present in the parent decomposition.

No SG01 output contradicts another G01 child contract: CityRecord preserves the proxy credentials SG02 consumes, and optional `wb_dest` preserves both the explicit-dest and no-forced-dest WB paths SG03 must implement.

Result: **SG01 vertical reverse compilation to G01 = PASS (contract model only).**

---

# Virtual execution compilation gate

Before implementation, execute each initial Prompt virtually in dependency order and verify:
1. its expected diff stays inside Task write scope;
2. output satisfies the Task contract exactly;
3. produced interfaces match downstream prerequisites without reinterpretation;
4. no hidden requirement for proxy runtime, cookies, scheduler, or result persistence is introduced;
5. no lifecycle contradiction exists (e.g. a source adapter destroys/changes data required by a downstream consumer);
6. tests/evidence distinguish invalid input from valid empty/optional values;
7. user city contract remains minimum sufficient.

A virtual mismatch changes this decomposition/contracts first. Prompt wording alone may not widen a Task.
