# G01.SG01 — virtual execution compile report

Parent: #31  
Vertical model: `docs/development/G01/SG01/vertical.md`  
Status: **SEMANTIC_COMPILE_PASS (SG01 vertical only)**

This report does not authorize implementation. Full G01 development remains blocked until SG02–SG06 are also vertically decomposed and the complete G01 virtual composition passes.

## Current-code facts used in simulation

1. `parser/core/cli.py` already loads products dynamically from CSV/Excel, PostgreSQL and `products.json` into `{wb: [...], ozon: [...]}`.
2. `parser/core/db.py` already owns `parser_skus` and provides `load_skus()`.
3. Current regions are legacy `config.json` records, not a file/DB `CitySet`.
4. Current legacy `review_profiles()` treats absent WB `dest` as invalid.
5. Current `repair_regions()` attempts browser/manual region repair and obtains missing WB `dest`.
6. Current `run_parsing()` skips WB entirely when `dest` is absent and requires Ozon profile cookies.

Facts 4–6 belong to later runtime/fallback Subgoals. SG01 must therefore create a normalized input boundary without routing it through those legacy gates.

---

# Prompt simulation

## P01 — PR01.ST01.T01 product source normalization

Expected virtual implementation:
- preserve current product file/DB/JSON loaders;
- optionally extract a small source module so product file and DB paths return the same canonical dict;
- add deterministic normalization/parity tests.

Expected output:
`ProductSet={"wb":[str...],"ozon":[str...]}`.

Compatibility:
- consumed directly by SG03/SG04/SG06 later;
- no lifecycle conflict;
- no write-scope conflict with city-only Tasks except optional shared model module, which can be serialized or kept entity-specific.

Verdict: **PASS**.

## P02 — PR02.ST01.T01 minimum CityRecord

Expected virtual implementation:
- small normalizer/model;
- validates `city`, `proxy`, `proxy_user`, `proxy_password`;
- missing/blank `wb_dest` => `None`;
- no extra required field.

Expected output:
canonical city mapping/list entry consumable by both source adapters and later SG02/SG03.

Compatibility:
- preserves proxy credentials needed by SG02;
- preserves explicit optional `wb_dest` needed by SG03;
- does not impose legacy profile/cookie fields.

Verdict: **PASS**.

## P03 — PR02.ST02.T01 city file source

Expected virtual implementation:
- CSV/Excel reader analogous to product file loader;
- each row normalized by P02 output;
- explicit row validation error;
- dummy sample fixture optional.

Expected output:
`CitySet` identical in shape to DB output.

Compatibility:
- no dependency on network or legacy profile state;
- adding a row changes data only.

Verdict: **PASS**.

## P04 — PR02.ST03.T01 city PostgreSQL source

Expected virtual implementation:
- extend existing `ParserDB._ensure_tables()` with idempotent `parser_cities`;
- add `load_cities()` using the same normalizer;
- user data columns: `city`, `proxy`, `proxy_user`, `proxy_password`, nullable `wb_dest`;
- generated DB mechanics may remain internal.

Expected output:
DB CitySet semantically equal to file CitySet.

Compatibility:
- existing ParserDB remains single DB abstraction;
- does not change result persistence ownership;
- no additional user field required.

Verdict: **PASS**.

## P05 — PR03.ST01.T01 source-neutral composition

Expected virtual implementation:
- one small orchestration/API boundary composing accepted ProductSet and CitySet adapters;
- supports product file/DB × city file/DB combinations;
- does not yet replace the runtime legacy-region loop.

Critical boundary discovered during compile:
`CitySet` MUST NOT be routed through current `review_profiles()`, `repair_regions()` or `add_new_regions()` in SG01 because those functions encode legacy profile/dest requirements. Runtime replacement belongs to SG02/SG03/SG05/SG06.

With that boundary, SG01 can finish without contradicting G01.A08.

Verdict: **PASS after explicit boundary clarification**.

## P06 — PR03.ST02.T01 SG01 closure suite

Expected virtual implementation:
- acceptance matrix tests all four source combinations;
- tests missing required city fields;
- tests omitted/blank `wb_dest`;
- proves semantic file/DB parity;
- detects accidental legacy-gate coupling.

Expected output:
Evidence map proving SG01 contract, not runtime marketplace behavior.

Verdict: **PASS**.

---

# Reverse assembly

## Prompt -> Task
Each Prompt has one exact Task identity, bounded output, bounded write scope, tests/evidence, dependencies and stop condition. No Prompt widens its Task.

**PASS**.

## Task -> Stage
- PR01.ST01.T01 fully supplies product normalized-source Stage.
- PR02.ST01.T01 supplies CityRecord contract.
- PR02.ST02.T01 supplies city file source.
- PR02.ST03.T01 supplies city DB source.
- PR03.ST01.T01 supplies unified handoff.
- PR03.ST02.T01 supplies SG01 closure evidence.

No Stage has an uncovered semantic responsibility.

**PASS**.

## Stage -> Process
PR01 = normalized dynamic products.  
PR02 = normalized dynamic cities from both sources.  
PR03 = source-neutral composition + parity/minimality proof.

**PASS**.

## Process -> SG01
SG01 acceptance coverage:
- product file -> PR01;
- product DB -> PR01;
- city file -> PR02.ST02;
- city DB -> PR02.ST03;
- source parity -> PR01 + PR02 + PR03;
- required city validation -> PR02.ST01;
- optional `wb_dest` -> PR02.ST01 + closure test;
- data-only add/change -> PR01/PR02 + PR03 proof;
- no extra required city field -> PR02.ST01 + PR03.ST02.

**PASS**.

## SG01 -> G01
SG01 outputs are compatible with remaining G01 children:
- SG02 receives proxy credentials without needing file/DB knowledge;
- SG03 receives optional `wb_dest`, including `None` as an intentional valid state;
- SG04 receives city/proxy context without legacy Ozon profile requirement;
- SG05 keeps legacy region/profile objects separate from new primary CitySet;
- SG06 can later select sources non-interactively and build the full matrix.

The critical current-code contradiction (`dest` absent -> legacy gate/skip) is not hidden; it is intentionally left to SG03/SG06 where runtime ownership belongs.

**SG01 -> G01 contribution PASS**.

---

# Gap / minimality check

No missing SG01 responsibility found.

No Task needs proxy network behavior, marketplace parsing, stock extraction, result persistence, automatic fallback or scheduler behavior.

No new mandatory user field is justified.

The proposed six-Task contour is minimum sufficient for separating:
1. existing product acquisition;
2. city contract;
3. city file source;
4. city DB source;
5. combined downstream handoff;
6. explicit closure proof.

Merging (2–4) would make source-specific failures harder to isolate; merging (5–6) would allow implementation to declare success without independent parity/minimality evidence.

## Final verdict
`G01.SG01`: **SEMANTIC_COMPILE_PASS** on the proposed vertical model.

Implementation is still **NOT AUTHORIZED** until the complete G01 contour (SG01–SG06) compiles end-to-end.
