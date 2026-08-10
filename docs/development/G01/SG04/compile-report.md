# G01.SG04 semantic compilation report — repaired C02

Parent: Issue #34
Planning branch: `brain/g01-regional-monitor-plan`
Active generation: `C02.I01`
Superseded generation: C01 (retained as history; invalid boundary: prohibited Selenium/Chrome in primary rather than prohibiting human interaction).

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_ENGINE_CONTEXT_PROBE_REQUIRED)`

The repaired C02 Prompt→Task→Stage→Process→SG04 structure is compositionally sufficient and now matches the intended product concept: hidden/headless Selenium/Chrome may participate in primary autonomous Ozon operation, while visible/manual browser work remains SG05 fallback/support.

This verdict does **not** claim live Ozon/browser behavior has already proven proxy binding or requested-city semantics. Runtime evidence remains owned by PR01/PR02.

## C02 repair finding

C01 had one structural error: it treated `Selenium/Chrome` as synonymous with manual legacy fallback. That would have blocked the intended hidden-browser autonomous mechanism.

C02 changes the discriminator:
- engine technology (`curl_cffi` vs Selenium/Chrome) does **not** determine primary/fallback ownership;
- **human interaction and manually maintained profile state** determine the SG04/SG05 boundary.

Therefore:
- automatic hidden/headless Selenium/Chrome = SG04 allowed;
- manual/visible login/PVZ/captcha/profile preparation = SG05 explicit legacy;
- no automatic crossing from SG04 failure into SG05.

## Current-code findings used by virtual execution

1. Existing `warm_region()` is manual/visible and therefore remains SG05 legacy, not the target hidden-browser engine.
2. Existing `browser_fetch_prices()` is an automatic call site today but uses a legacy visible/profile flow that may require human captcha handling; primary C02 must not reuse that behavior as implicit repair.
3. Existing `ozon.fetch_price()` is lightweight `curl_cffi` and useful where current runtime permits it.
4. Existing `parse_price()` is already a strong engine-neutral semantic boundary because it targets requested-product `webPrice` state.
5. SG02 already produces canonical city-bound `ProxyContext`. Its two current HTTP adapters do not prevent SG04 from implementing an Ozon-specific browser adapter, provided that adapter consumes the same ProxyContext and never creates a second proxy authority.

## Virtual execution of active C02 Prompts

### PR01 — evidence and engine contract
`PR01.ST01.T01.C02.I01` probes no-legacy Ozon behavior with `curl_cffi` and, when evidence requires it, hidden/headless Selenium/Chrome. Browser proxy binding itself is an evidence requirement. No human action is allowed.

`PR01.ST02.T01.C02.I01` chooses only an evidenced engine strategy: HTTP-only, browser-only or bounded combination. It does not assume HTTP-first/browser-first. Requested-city verification remains independent and mandatory.

Expected fail-closed outputs:
- `OZON_CONTEXT_CONTRACT_UNPROVEN`;
- `OZON_BROWSER_PROXY_BINDING_UNPROVEN`;
- `OZON_REGION_CONTEXT_UNPROVEN`.

### PR02 — autonomous OzonContext engine
`PR02.ST01.T01.C02.I01` can construct session/location state using the evidenced engine strategy. Hidden browser consumes ProxyContext, has bounded lifecycle and zero human interaction. Automatic cookies may be reused/transferred only when evidenced.

`PR02.ST02.T01.C02.I01` verifies requested city and performs bounded automatic refresh/rebootstrap through the same engine strategy and same ProxyContext. Human-action-required challenge is an explicit primary failure.

### PR03 — engine-neutral price semantics
`PR03.ST01.T01.C02.I01` receives normalized accepted content/state and preserves requested-product `webPrice` semantics independent of HTTP/browser engine.

`PR03.ST02.T01.C02.I01` separates HTTP transport, browser startup/proxy/navigation/lifecycle, context, session/anti-bot and semantic failures. No broad synthetic `403` collapse.

### PR04 — collector and closure
`PR04.ST01.T01.C02.I01` allows primary collector to invoke the accepted hidden browser engine automatically, but does not call legacy `warm_region`/`browser_fetch_prices` as hidden manual repair. One outcome remains required per requested Ozon SKU × city.

`PR04.ST02.T01.C02.I01` proves first/repeated operation with zero human action, including browser proxy binding/lifecycle where applicable, and reverse-composes C02 to SG04/G01.

## Reverse composition — internal SG04

- PR01 produces an evidenced autonomous-engine + requested-city verification contract.
- PR02 produces an autonomous city-bound OzonContext, optionally hidden-browser-backed.
- PR03 produces engine-neutral requested-SKU price semantics and typed failures.
- PR04 produces product×city accounting and no-human-work repeated-run evidence.

No SG04 acceptance clause is orphaned.

## Cross-subgoal reverse check

### SG02 → SG04
PASS.
SG02 remains canonical ProxyContext authority. SG04 browser-specific adaptation is an Ozon context implementation detail, not a new proxy source of truth. No SG02 task needs widening.

### SG04 ↔ SG05
PASS after C02 repair.
The boundary is now semantic rather than library-based:
- SG04: autonomous, zero-human, proxy-bound hidden browser allowed;
- SG05: explicit visible/manual profile-cookie/browser fallback/support.
Existing SG05 contract remains valid because it preserves the **old manual legacy capability** and forbids implicit primary fallback; it never needs exclusive ownership of Selenium as a library.

### SG04 → G01
C02 continues to contribute to:
- A01 autonomous primary operation;
- A07 Ozon regional price;
- A10 failure isolation;
- A11 repeated operation without manual regional authorization;
- A12 complete-matrix Ozon contribution.

Allowing hidden browser strengthens, rather than weakens, A01/A11 because autonomy is defined by absence of human maintenance, not absence of a browser process.

## Required runtime gates

### R1 — Autonomous engine contract
Prove which engine/sequence current Ozon requires from a no-legacy state.
Failure: `OZON_CONTEXT_CONTRACT_UNPROVEN`.

### R2 — Hidden-browser proxy binding (conditional)
If hidden Selenium/Chrome is used, prove all browser traffic/authentication derives from requested-city ProxyContext and does not silently go direct.
Failure: `OZON_BROWSER_PROXY_BINDING_UNPROVEN`.

### R3 — Requested-city verification
Prove an observable signal sufficient to bind effective Ozon context to requested city; proxy geolocation alone is not automatically enough.
Failure: `OZON_REGION_CONTEXT_UNPROVEN`.

### R4 — Zero-human repeatability
Prove first run and repeated refresh/rebootstrap require no login, manual PVZ/city choice, Enter, visible-window prerequisite or human captcha solve. Human-required challenge must fail explicitly.

If a runtime gate fails, SG04 cannot fake PASS. If resolution requires new user-supplied city data, repair G01/SG01 contracts and recompile.

## Scope boundaries preserved
- SG02: ProxyContext/auth transport authority.
- SG03: WB.
- SG04: autonomous Ozon context engine + regional verification + price semantics.
- SG05: explicit manual/visible legacy fallback/support.
- SG06: persistence, full matrix orchestration and scheduler-ready run.

## Global state
SG04 C02 is vertically compiled. Implementation remains blocked until SG06 is vertically compiled and the complete SG01–SG06 contour is reverse-compiled to G01.