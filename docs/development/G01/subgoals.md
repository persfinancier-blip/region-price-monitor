# G01 — Proposed Subgoal Decomposition

Parent: Issue #30 / `docs/development/G01/goal.md`

Status: **PROPOSED — SG-level decomposition only**

This document does not authorize implementation. Processes, Stages, Tasks and Prompts are still absent; full Semantic / Virtual Compilation therefore has not yet been performed.

## Global decomposition invariants

1. Canonical implementation remains in `persfinancier-blip/region-price-monitor`.
2. Existing useful behavior is reused where possible; rewrites require necessity.
3. The local `C:\Dev\parser\_wb\_ozon\_delivery` and `Price-monitor` are reference/source inputs, not parallel production implementations.
4. The new primary path is proxy-first. Existing browser/cookies/profile behavior remains fallback.
5. User-facing inputs stay minimal. No new required city fields without demonstrated necessity.
6. A child contract is valid only if its output contributes to a parent contract.

---

# SG01 — Dynamic Products and Cities Input

## Purpose

Give the parser one normalized input layer for products and cities, with both lists loadable from file or PostgreSQL and without hardcoded operational entries.

## Input Contract

Available configured source for products and available configured source for cities.

Product source: existing supported product identifiers and marketplace association.

City source record minimum:

```text
city             required
proxy            required
proxy_user       required
proxy_password   required
wb_dest          optional
```

## Output Contract

```text
ProductSet
CitySet
```

where every accepted city has the minimum fields above, `wb_dest` may be absent, and downstream code does not depend on whether records originated from file or DB.

No city, product or proxy value required for normal operation is hardcoded in parser source.

## Acceptance Criteria

- products load from file;
- products load from DB;
- cities load from file;
- cities load from DB;
- identical downstream normalized contract for file and DB sources;
- missing `wb_dest` is valid;
- missing required proxy authentication/connectivity fields is a clear input error;
- adding a city or product requires only source-data modification, not code modification.

## Evidence

- loader unit/contract tests for both source types;
- representative file and DB fixtures;
- normalized object comparison across equivalent file/DB inputs;
- negative tests for missing required fields;
- test proving omitted `wb_dest` is accepted.

## Failure Conditions

- cities remain stored only in config/code;
- DB or file city source is missing;
- downstream code has separate incompatible city models for file and DB;
- `wb_dest` becomes required;
- extra user fields are required without necessity.

---

# SG02 — Proxy-First Regional Transport

## Purpose

Provide the shared primary transport that executes marketplace traffic through the mobile proxy assigned to each city without requiring a manually warmed browser profile.

## Input Contract

```text
CityRecord
Marketplace request specification
```

CityRecord supplies:

```text
city
proxy
proxy_user
proxy_password
wb_dest?
```

## Output Contract

A marketplace request context/transport bound to the selected city's authenticated proxy, plus a structured request outcome that distinguishes successful response from transport/proxy/HTTP failure.

The primary transport itself does not require manual browser interaction or pre-existing city cookies.

## Acceptance Criteria

- configured proxy authentication is actually applied to requests;
- WB and Ozon collectors can consume the transport/context;
- a proxy failure is explicit and not converted to empty business data;
- normal primary execution does not call manual warming/profile-selection code;
- proxy credentials are not emitted into result records or ordinary logs.

## Evidence

- transport tests with inspected proxy configuration;
- failure-path tests for authentication/connectivity errors;
- integration proof that collectors receive the city-bound transport;
- proof that primary execution path has no manual warm dependency.

## Failure Conditions

- proxy fields are loaded but ignored;
- one marketplace bypasses the configured city proxy on its primary path;
- proxy failure is returned as valid zero/empty marketplace data;
- primary path still requires manually prepared cookies/profile.

---

# SG03 — Wildberries Regional Price and Stock

## Purpose

Upgrade the existing WB API path so each requested `product × city` returns regional price and regional stock/availability through SG02.

## Input Contract

```text
WB ProductSet subset
CityRecord
Proxy-first transport/context
```

`wb_dest` is optional.

## Output Contract

For every requested WB product/city unit:

```text
marketplace = wb
product identifier
city
price
stock / availability
status / error
```

If `wb_dest` exists, it is sent explicitly. If it does not exist, the request uses WB default/region behavior without treating omission as an error.

The chosen stock/availability value is derived from the existing working WB endpoint response with minimum sufficient interpretation.

## Acceptance Criteria

- regional WB price returned for valid request;
- stock/availability extracted from the same or directly associated working endpoint data;
- valid zero stock is distinguishable from request/parser failure;
- `wb_dest` present path works;
- `wb_dest` absent path is valid and executes without forced placeholder value;
- requests use the city proxy transport.

## Evidence

- captured/fixture WB responses covering price, positive stock, zero stock and error;
- parser contract tests;
- integration tests with and without `wb_dest`;
- proof of proxy use in WB primary path.

## Failure Conditions

- only price is returned;
- stock is inferred from price rather than endpoint stock/availability data;
- missing `wb_dest` aborts the city;
- errors become zero stock;
- WB primary path bypasses proxy transport.

---

# SG04 — Ozon Proxy-First Regional Price

## Purpose

Replace manual city-cookie warming as the normal Ozon regional-price path with an autonomous proxy-first collection flow.

## Input Contract

```text
Ozon ProductSet subset
CityRecord
Proxy-first transport/context
```

## Output Contract

For every requested Ozon product/city unit:

```text
marketplace = ozon
product identifier
city
regional price
status / error
```

The normal path requires no user action to open Ozon and switch city before repeated collection.

If Ozon technically requires session/context bootstrap beyond the proxy, that bootstrap must be automatic inside the primary path and must not introduce new mandatory user fields unless later decomposition proves them unavoidable.

## Acceptance Criteria

- Ozon requests use the selected city proxy;
- regional price is obtained without manually pre-warmed city cookies in the normal path;
- any required session bootstrap is automatic;
- transport/HTTP/parse failure remains explicit;
- repeated runs do not require user browser action.

## Evidence

- Ozon fixture/integration responses for successful regional price and failures;
- end-to-end primary-path test starting without manually warmed city profile;
- repeat-run test using the same configured city input;
- proof of proxy binding.

## Failure Conditions

- normal Ozon run still says to open browser/select city/update cookies;
- proxy is configured but Ozon bypasses it;
- Ozon failure is represented as a valid price/value;
- solution adds manual per-city preparation under another name.

---

# SG05 — Legacy Regional Fallback Preservation

## Purpose

Preserve the current browser/cookies/profile regional mechanism as a usable reserve path while ensuring it is no longer the required normal path.

## Input Contract

Existing legacy warm/profile/cookies functionality and its existing configuration/artifacts.

## Output Contract

A clearly reachable fallback mode/capability that can still execute the preserved legacy regional flow without being invoked as a prerequisite of proxy-first collection.

Automatic fallback selection is not required by G01 unless later decomposition demonstrates it is necessary; preservation and explicit availability are sufficient.

## Acceptance Criteria

- existing usable legacy path is not deleted;
- fallback can be invoked intentionally;
- primary mode does not require fallback preparation;
- fallback artifacts are separated from primary input requirements;
- existing legacy behavior has regression coverage sufficient to detect accidental breakage.

## Evidence

- regression test/smoke evidence for legacy entrypoint;
- primary-path test with no legacy profile present;
- code/config mapping showing primary and fallback separation.

## Failure Conditions

- legacy path removed or silently broken;
- fallback becomes mandatory initialization for primary mode;
- primary city contract starts requiring legacy profile paths/cookies.

---

# SG06 — Complete Matrix Run, Persistence and Repeatable Autonomous Operation

## Purpose

Compose SG01–SG05 into one operational parser run that processes the requested matrix, records every unit outcome, persists results, and can be launched repeatedly without interactive city preparation.

## Input Contract

```text
ProductSet from SG01
CitySet from SG01
WB collector from SG03
Ozon collector from SG04
Fallback capability from SG05
Configured output target: file and/or PostgreSQL
```

## Output Contract

A complete RunResult set for the planned matrix:

```text
Products × Cities × enabled Marketplaces
```

Each planned unit has either a successful business result or explicit failure status.

Persisted minimum result fields:

```text
timestamp
marketplace
product identifier
city
price
status / error
```

WB additionally persists:

```text
stock / availability
```

The primary operational entrypoint supports repeat/non-interactive execution after configuration, so an external scheduler can launch it without answering prompts or warming city profiles.

## Acceptance Criteria

- matrix expansion covers every requested product/city for its marketplace;
- failure of one unit does not silently erase unrelated units;
- every planned unit is accounted for as success or explicit error;
- file output works where already supported;
- PostgreSQL output works where already supported;
- city and product identity remain attached to persisted results;
- WB stock/availability survives persistence;
- repeated primary runs require no manual city interaction;
- a non-interactive/scheduler-ready primary invocation exists.

## Evidence

- deterministic matrix fixture with expected unit count;
- mixed success/failure integration run;
- file persistence verification;
- PostgreSQL persistence verification;
- repeated-run test;
- non-interactive invocation test.

## Failure Conditions

- missing city/product combinations disappear without status;
- one failed city aborts the entire result without accounting;
- WB stock is collected but lost before persistence;
- primary run requires interactive prompts every cycle;
- scheduler launch cannot run from existing configuration/source data alone.

---

# SG -> G01 Contract Compilation Check

This is a **decomposition completeness check**, not the final Prompt-level Semantic Compilation.

| G01 requirement | Child output(s) that assemble it |
|---|---|
| Products from file/DB | SG01 |
| Cities from file/DB | SG01 |
| Minimal city proxy contract | SG01 + SG02 |
| No hardcoded operational city/product values | SG01 |
| Proxy-first primary path | SG02 |
| WB regional price | SG03 |
| WB stock/availability | SG03 |
| Optional `wb_dest` | SG01 + SG03 |
| Ozon proxy-first regional price | SG02 + SG04 |
| No manual Ozon city warming in normal operation | SG04 + SG06 |
| Legacy cookies/profile preserved as fallback | SG05 |
| Explicit error vs zero/valid value | SG02 + SG03 + SG04 + SG06 |
| Complete `Products × Cities × Marketplaces` accounting | SG06 |
| File/DB persistent results | SG06 |
| Repeatable scheduler-ready operation | SG06 |
| One canonical implementation in `region-price-monitor` | global invariant across SG01–SG06 |

## SG-level result

**PASS — no G01 output-contract element is currently orphaned at SG level.**

The proposed subgoals are also minimally separated by responsibility:

```text
SG01  inputs
  -> SG02  regional transport
       -> SG03  WB
       -> SG04  Ozon
SG05  legacy fallback preservation
SG01 + SG03 + SG04 + SG05
  -> SG06  complete operational run and persistence
```

This PASS means only that the six proposed subgoals can compositionally cover G01. It does **not** mean the architecture or implementation is proven. The next required step is decomposition of each SG into Processes, followed by the same parent-contract compilation check.