# G01 — Full Application Simulation from 43 Active Prompts

Repository: `persfinancier-blip/region-price-monitor`  
Planning branch: `brain/g01-regional-monitor-plan`  
Source generation: all **43 active Prompt files** from SG01–SG06.  
Purpose: model the application that would exist if every active Prompt were executed successfully in dependency/write-scope order, then test that virtual application against G01 rather than merely re-checking decomposition.

## Verdict

**`APPLICATION_SIMULATION_PASS_WITH_RUNTIME_EVIDENCE_GATES`**

The 43 Prompt outputs compose into one coherent runnable application architecture. The modeled application satisfies the G01 behavioral contract **if** the external/runtime evidence gates succeed. The Prompt set does not contain an internal software/interface contradiction after the SG02 C02, SG04 C02 and SG05 C02 repairs.

This is **not** an unconditional statement that current WB/Ozon production behavior is already proven. Runtime facts that cannot be derived from repository text remain fail-closed gates.

## Active Prompt generation used

- SG01: 6 active Prompts (`C01.I01`)
- SG02: 6 active Prompts: #50–#53 `C01.I01`, #54–#55 `C02.I01`
- SG03: 7 active Prompts (`C01.I01`)
- SG04: 8 active Prompts (`C02.I01`)
- SG05: 6 active Prompts (`C02.I01`)
- SG06: 10 active Prompts (`C01.I01`)
- Total: **43**

Superseded Prompt files were not treated as active implementation instructions.

---

# 1. Virtual generated application

The most likely minimum-sufficient resulting code organization is conceptually:

```text
parser/core/
  input_models.py        # ProductSet/CityRecord canonical models/normalizers
  product_sources.py     # file/DB product adapters (or equivalent refactor)
  city_sources.py        # file/DB city adapters
  inputs.py              # source-neutral ProductSet + CitySet handoff

  transport.py           # ProxyContext, safe projection/redaction, TransportOutcome
  requests_transport.py  # WB HTTP adapter (may be folded into transport.py)
  curl_transport.py      # Ozon HTTP adapter (may be folded into transport.py)

  wb.py                  # request builder, optional dest, price/stock parser,
                         # per-SKU typed outcomes/collector

  ozon.py                # engine-neutral webPrice parser and HTTP path
  ozon_context.py        # autonomous OzonContext engine / city verification
                         # curl_cffi and/or hidden Selenium, evidence-selected

  warm_browser.py        # preserved authenticated legacy/manual support
                         # personalized user-cookie fallback remains usable

  run_models.py          # RunPlan, AccountedOutcome, RunResult (name may vary)
  runner.py              # primary orchestration (name may vary)
  storage.py             # canonical complete run CSV + legacy compatibility
  db.py                  # parser_skus + parser_cities + migrated parser_results
  collect.py / run_primary.py
                         # zero-stdin scheduler-ready primary entrypoint
```

Exact filenames are implementation choices; semantic ownership is constrained by the Prompts.

## Core data flow

```text
product source ─┐
                ├─> ProductSet ─┐
city source ────┘               │
                                ├─> RunPlan (complete expected matrix)
CitySet ─> ProxyContext/city ───┤
                                │
             ┌──────────────────┴──────────────────┐
             │                                     │
          SG03 WB                              SG04 Ozon
      requests transport              curl_cffi / hidden browser
      optional wb_dest                   verified OzonContext
      evidenced stock                         webPrice
             │                                     │
             └────────── typed outcomes ────────────┘
                                │
                         reconciliation
                                │
                     exactly one terminal outcome
                     per (marketplace, sku, city)
                                │
                           RunResultSet
                         ┌──────┴──────┐
                         │             │
                       CSV        PostgreSQL
```

SG05 is intentionally outside this automatic primary graph:

```text
explicit operator legacy mode
  -> current user-authenticated Ozon profile
  -> personalized cookies/tokens
  -> legacy curl/browser path
```

Primary failure does not automatically cross into SG05.

---

# 2. Prompt-by-Prompt modeled build result

## SG01 — input layer

Executing the six SG01 Prompts yields:
- normalized `ProductSet={"wb": [...], "ozon": [...]}`;
- canonical CityRecord with exactly `city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`;
- CSV/Excel and PostgreSQL city adapters;
- idempotent `parser_cities` support;
- one source-neutral input bundle;
- no route through legacy profile/dest warming.

Virtual compile: **PASS**.

## SG02 — proxy authority

Executing the six active SG02 Prompts yields:
- one authenticated/redacted `ProxyContext` constructed from CityRecord;
- one safe typed `TransportOutcome` family;
- `requests` adapter for current WB HTTP;
- `curl_cffi` adapter for current Ozon HTTP;
- no silent direct fallback;
- SG04 hidden-browser proxy projection derived from the same ProxyContext, without requiring browser traffic to transit curl_cffi.

Virtual compile: **PASS**.

## SG03 — WB

Executing the seven SG03 Prompts yields two possible runtime branches.

### Evidence-success branch
- current WB consumer response is captured/sanitized;
- exact stock semantics are proven;
- price/stock normalization is defined from evidence;
- `wb_dest` is omitted when absent rather than guessed;
- every request uses ProxyContext;
- every requested SKU gets one typed result;
- zero stock is valid data, not an error;
- missing SKU/transport/parser errors remain explicit.

Application compatibility: **PASS**.

### Evidence-failure branch
If the current endpoint cannot prove trustworthy stock semantics:
`WB_STOCK_CONTRACT_UNPROVEN`.

The application remains internally safe but **G01 runtime acceptance fails A06**. It must not fake stock.

## SG04 — new Ozon proxy-first mechanism

Executing the eight active SG04 C02 Prompts yields an `OzonContext` engine selected only from runtime evidence:
- curl_cffi only, or
- hidden/headless Selenium/Chrome only, or
- bounded deterministic combination.

The hidden browser is not legacy merely because it is Selenium. It is primary when it is:
- automatic;
- zero-human;
- bound to the requested city's ProxyContext;
- bounded/cleaned up;
- independent of SG05 personalized cookies/profile.

The price parser consumes normalized content/state and preserves current requested-product `webPrice` semantics.

A successful Ozon result requires **verified effective requested-city context**.

Possible runtime blockers:
- `OZON_CONTEXT_CONTRACT_UNPROVEN`;
- `OZON_BROWSER_PROXY_BINDING_UNPROVEN`;
- `OZON_REGION_CONTEXT_UNPROVEN`.

If any is permanent for the intended environment, the application remains fail-closed but **G01 runtime acceptance fails A07/A01/A11 for Ozon**.

## SG05 — current working reserve

Executing the six active SG05 C02 Prompts preserves:
- current personalized authenticated Ozon cookies/tokens from confirmed user login;
- current profile/cookie loading semantics;
- intentional `warm_region` authenticated profile refresh;
- legacy browser/curl behavior;
- optional manual WB dest support.

It removes these mechanisms from implicit primary startup/failure repair but does not delete them.

If a Worker replaces authenticated legacy cookies with generic anonymous cookies, SG05 fails `LEGACY_AUTH_COOKIE_SEMANTICS_LOST`.

Virtual compile: **PASS**, live authenticated desktop smoke still required.

## SG06 — actual application/run layer

Executing the ten SG06 Prompts yields:
- RunPlan created before networking;
- one planned key per `(marketplace, sku, city)`;
- reconciliation that synthesizes explicit `missing_outcome` instead of losing units;
- canonical RunResult rows;
- complete run-level CSV including failures;
- migrated PostgreSQL results including `city/status/error/stock_qty/nullable is_available`;
- no old `is_available=True` fallback for failed/unknown rows;
- per-city ProxyContext orchestration;
- no `_enrich()` success-only filtering;
- zero-stdin scheduler-ready primary command;
- independent repeated runs/run_ids;
- file/PG parity evidence.

Virtual compile: **PASS**.

---

# 3. Concrete simulated run

Example configured input:

```text
Products:
  WB:   WB1, WB2
  Ozon: OZ1

Cities:
  Moscow -> proxy A -> wb_dest present
  Kazan  -> proxy B -> wb_dest absent
```

RunPlan is created before requests:

```text
WB1 × Moscow
WB2 × Moscow
OZ1 × Moscow
WB1 × Kazan
WB2 × Kazan
OZ1 × Kazan
```

`planned_count = 6`.

Injected virtual outcomes:

```text
WB1 Moscow -> success, stock=8
WB2 Moscow -> success, stock=0
OZ1 Moscow -> success, verified Moscow context
WB1 Kazan  -> success, no dest parameter, stock=3
WB2 Kazan  -> proxy timeout
OZ1 Kazan  -> context_unproven
```

Reconciliation result:

```text
terminal_count = 6
```

No unit disappears. WB zero stock remains a valid row. Proxy timeout remains a failure row. Ozon unproven city cannot become a price row.

The same six canonical RunResult rows are written to the run CSV and, when PG persistence succeeds, to `parser_results` under the same run_id.

The run is considered operationally completed even with unit-level marketplace failures; fatal configuration/plan/persistence failure is distinct at process-exit level.

A second run creates a distinct run_id and does not require city/profile/cookie preparation in primary mode.

---

# 4. Failure-injection simulation

## Proxy credentials invalid for one city
Expected: typed proxy/auth failures only for affected units; sibling city remains processed. **PASS**.

## WB returns HTTP error/empty response
Expected: transport/accounting failures, not an empty successful city. **PASS**.

## WB omits one requested SKU
Expected: explicit SKU-scoped missing/not-present outcome; siblings remain. **PASS**.

## WB stock = 0
Expected: successful data row with zero stock and false availability under evidenced semantics. **PASS**.

## WB stock schema changed
Expected: explicit malformed/schema failure or runtime evidence blocker, never stock inferred from price. **PASS fail-closed; G01 A06 runtime may fail**.

## Ozon lightweight HTTP blocked
Expected: use hidden browser only if PR01 runtime evidence selected that strategy. **PASS by architecture**.

## Hidden Chrome cannot authenticate/bind selected proxy
Expected: `OZON_BROWSER_PROXY_BINDING_UNPROVEN`, never direct traffic. **PASS fail-closed; Ozon runtime goal may fail**.

## Ozon returns a page but requested city cannot be proven
Expected: `OZON_REGION_CONTEXT_UNPROVEN`, never mislabeled price. **PASS fail-closed; G01 A07 runtime fails for that unit/environment**.

## Ozon requires human captcha
Expected: typed autonomous-path failure; primary does not wait for user and does not silently enter SG05. **PASS**.

## Current legacy authenticated cookies expire
Expected: explicit legacy maintenance/auth failure; operator may intentionally run `warm_region` to refresh. Primary unaffected. **PASS**.

## PostgreSQL unavailable
Expected: explicit persistence failure according to selected output policy; PG acceptance cannot be faked. Complete file target can still be tested independently. **PASS fail-closed**.

## One collector returns `[]`
Expected: RunPlan reconciliation produces terminal failures for missing planned keys. **PASS**.

---

# 5. Goal compliance simulation

| Goal AC | Modeled final application |
|---|---|
| A01 repeat without manual city switching | PASS structurally; Ozon runtime engine must prove zero-human operation |
| A02 products dynamic file/DB | PASS |
| A03 cities dynamic file/DB | PASS |
| A04 minimum city/proxy contract | PASS structurally; runtime proxy/provider compatibility must prove it is usable |
| A05 WB regional price | PASS in evidenced runtime branch |
| A06 WB regional stock/availability | CONDITIONAL on WB endpoint stock proof |
| A07 Ozon regional price | CONDITIONAL on autonomous engine + city-verification proof |
| A08 `wb_dest` absent valid | PASS: omitted from request, city remains planned |
| A09 current legacy authenticated fallback preserved | PASS structurally; authenticated desktop smoke required |
| A10 errors not valid values | PASS |
| A11 repeated cycle no manual regional setup | PASS structurally; Ozon runtime proof required |
| A12 complete matrix accounting | PASS |

## Product-level conclusion

### Does the 43-Prompt application compile into a coherent program?
**YES.**

No remaining internal Prompt/interface/lifecycle contradiction was found in this full application synthesis.

### Does it correspond to the original G01 goal?
**YES, structurally and behaviorally.**

The generated application's main path is the requested city-proxy-first monitor; products/cities are data-driven; WB includes stock; Ozon is autonomous when its runtime mechanism is provable; old authenticated cookies/profile behavior is preserved as reserve; output is a complete matrix with explicit errors.

### Can we assert today that it will definitely obtain correct live WB/Ozon data for every configured city?
**NO — not until runtime evidence Tasks execute.**

The uncertainty is external-marketplace behavior, not an unresolved internal software assembly problem.

Required live gates before final runtime PASS:
1. WB current consumer endpoint: exact stock semantics and supported no-forced-dest behavior (#60/#61/#66).
2. Ozon: autonomous engine strategy, hidden-browser proxy binding if needed, and requested-city verification (#71/#72/#78).
3. Current personalized-authenticated fallback desktop smoke (#86/#87).
4. PostgreSQL schema/migration/round-trip and full mixed run (#96/#100).

## Final application-simulation verdict

`APPLICATION_SIMULATION_PASS_WITH_RUNTIME_EVIDENCE_GATES`

Recommended next state: implementation may proceed exactly in the dependency/write-scope order from `full-compile-report.md`; runtime evidence gates execute at their point of use and retain authority to stop/repair the contour.
