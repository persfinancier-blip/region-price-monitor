# G01 — Canonical Subgoal Decomposition

Parent: Issue #30 / `docs/development/G01/goal.md`
Planning PR: #37

## Current status

All six Subgoals are decomposed vertically through Process -> Stage -> Task -> Prompt and have durable GitHub Issues/Prompt files.

Whole-contour report: `docs/development/G01/full-compile-report.md`.

Current proposed-generation verdict:

**`SEMANTIC_COMPILE_PASS (WHOLE G01 PROPOSED GENERATION)`**

This authorizes controlled execution of the planned development Tasks. It does not claim runtime marketplace/desktop/PostgreSQL acceptance has already passed; point-of-use evidence gates remain fail-closed.

## Global invariants

1. Canonical implementation repository is `persfinancier-blip/region-price-monitor`.
2. GitHub contracts/issues/prompts are durable authority; chat summaries are not source of truth.
3. Primary regional path is proxy-first.
4. Primary city input stays minimal:
   - `city` required;
   - `proxy` required;
   - `proxy_user` required;
   - `proxy_password` required;
   - `wb_dest` optional.
5. SG02 `ProxyContext` is the single proxy routing/auth authority for primary network engines.
6. Errors never become valid-looking price/zero-stock/availability data.
7. Existing useful current behavior is preserved where required; legacy Ozon personalized authenticated cookies/profile remain SG05 fallback-only.
8. Automatic legacy fallback switching is not required by G01 and must not be introduced implicitly.
9. Runtime evidence that disproves a contract causes structural repair/recompilation, not hidden Prompt widening.

---

# SG01 — Dynamic Products and Cities Input / Issue #31

Active generation: six `C01.I01` Prompts; Processes #38–#40; Tasks #41–#46.
Vertical: `docs/development/G01/SG01/vertical.md`.

## Purpose
Provide normalized dynamic ProductSet and CitySet from file or PostgreSQL without hardcoded operational city/product/proxy values.

## Input
Configured product source + configured city source.

## Output
- `ProductSet = {wb:[...], ozon:[...]}`;
- `CitySet` of canonical CityRecords using the minimum fields above.

## Acceptance
Products file/DB; cities file/DB; source-neutral downstream shape; omitted `wb_dest` valid; missing required proxy fields explicit; data changes require no code changes; primary CitySet not routed through legacy profile/dest warming gates.

## Verdict
`SEMANTIC_COMPILE_PASS`.

---

# SG02 — Proxy-First Regional Transport / Issue #32

Processes #47–#49; Tasks #50–#55.
Active generation:
- #50–#53: `C01.I01`;
- #54–#55: repaired `C02.I01`.
Repair: `docs/development/G01/SG02/C02-repair.md`.

## Purpose
Provide one authenticated/redacted city-bound `ProxyContext` plus typed transport failures and current HTTP adapters.

## Input
Canonical CityRecord + caller-owned request specification.

## Output
- single `ProxyContext` authority;
- typed/redacted HTTP transport outcome;
- `requests` adapter for current WB HTTP;
- `curl_cffi` adapter for current Ozon HTTP;
- cross-engine rule that any SG04 hidden browser derives its proxy settings from the same ProxyContext.

## Acceptance
Proxy authentication actually applied; no direct fallback under supplied ProxyContext; failures explicit; credentials redacted; no `wb_dest`, browser profile or cookie prerequisite for transport; no new CityRecord field.

Important C02 boundary: SG04 hidden/headless Selenium/Chrome does **not** need to transit through curl_cffi. Browser-specific proxy adaptation is SG04-owned but may not create a second proxy credential authority.

## Verdict
`SEMANTIC_COMPILE_PASS` after C02 repair.

---

# SG03 — Wildberries Regional Price and Stock / Issue #33

Processes #56–#59; Tasks #60–#66; seven active `C01.I01` Prompts.
Vertical: `docs/development/G01/SG03/vertical.md`.

## Purpose
Return regional WB price plus endpoint-evidenced stock/availability for every requested WB product/city through SG02.

## Input
WB ProductSet subset + CityRecord + SG02 ProxyContext. `wb_dest` optional.

## Output
Per requested WB unit:
- marketplace/product/city identity;
- price;
- stock quantity/availability as evidenced by current endpoint;
- status/error.

If `wb_dest` exists it is sent; if absent the `dest` parameter is omitted rather than blocking the city.

## Acceptance
Price + real stock semantics; zero stock distinct from failure; with/without dest; city proxy used; every requested WB unit accountable.

## Runtime gate
#60 must prove the current consumer endpoint stock schema/semantics. If not: `WB_STOCK_CONTRACT_UNPROVEN`; no guessed stock parser.

## Verdict
`SEMANTIC_COMPILE_PASS (RUNTIME_PROBE_REQUIRED)`.

---

# SG04 — Ozon Proxy-First Regional Price / Issue #34

Processes #67–#70; Tasks #71–#78; eight active `C02.I01` Prompts. C01 is superseded history.
Vertical: `docs/development/G01/SG04/vertical.md`.

## Purpose
Implement the **new** autonomous Ozon proxy-first mechanism without requiring the personalized authenticated cookies/profile used by the current fallback.

## Input
Ozon ProductSet subset + CityRecord + SG02 ProxyContext authority.

## Output
One typed Ozon price/failure outcome for every requested product/city from an accepted requested-city context.

## Autonomous engine boundary
Runtime evidence may select:
- curl_cffi;
- hidden/headless Selenium/Chrome;
- a bounded evidence-driven combination.

Hidden browser is allowed in primary when it requires zero human interaction and uses browser proxy settings derived from SG02 ProxyContext.

Forbidden in primary: manual login, manual city/PVZ selection, Enter prompts, visible-window prerequisite, human captcha solve, manually maintained per-city profile/cookies, or dependency on SG05 personalized authenticated cookies.

Ordinary automatically issued technical HTTP/browser session state is allowed and is not the legacy authenticated user session.

## Runtime gates
- autonomous engine/sequence evidence;
- hidden-browser ProxyContext binding if browser is used (`OZON_BROWSER_PROXY_BINDING_UNPROVEN` on failure);
- requested-city verification (`OZON_REGION_CONTEXT_UNPROVEN` on failure);
- first/repeated zero-human operation.

## Verdict
`SEMANTIC_COMPILE_PASS (RUNTIME_ENGINE_CONTEXT_PROBE_REQUIRED)`.

---

# SG05 — Legacy Regional Fallback Preservation / Issue #35

Processes #79–#81; Tasks #82–#87; six active `C02.I01` Prompts. C01 is superseded history.
Vertical: `docs/development/G01/SG05/vertical.md`.

## Purpose
Preserve the **currently working** browser/profile/cookies regional mechanism as explicit reserve/support without making it a prerequisite of the new primary path.

## Critical compatibility invariant
The current Ozon fallback requires **personalized authenticated cookies/tokens obtained after user-confirmed Ozon login**. These are secret runtime material and are not interchangeable with anonymous/generated cookies.

This personalized authenticated requirement belongs to SG05 fallback only; SG04 new proxy-first is independent from it.

## Output
Explicitly invokable authenticated Ozon fallback + operator support/refresh tools, including current profile/cookie flow and optional manual WB dest discovery.

## Acceptance
Current authenticated cookie/profile semantics preserved; invalid/expired fallback auth explicit; operator can intentionally refresh legacy login/profile; no raw tokens/cookies in Git/log/results/evidence; primary never invokes fallback implicitly; missing wb_dest stays valid primary input.

## Runtime gate
Visible desktop smoke using runtime-local authenticated profile/cookies without capturing secrets.

## Verdict
`SEMANTIC_COMPILE_PASS (LEGACY_AUTHENTICATED_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`.

---

# SG06 — Complete Matrix Run, Persistence and Autonomous Operation / Issue #36

Processes #88–#91; Tasks #92–#101; ten active `C01.I01` Prompts.
Vertical: `docs/development/G01/SG06/vertical.md`.

## Purpose
Compose SG01–SG05 into one primary run that creates the complete expected matrix before collection, accounts one terminal outcome per planned key, persists every outcome, and runs repeatedly/non-interactively.

## Input
ProductSet + CitySet + SG02 ProxyContext authority + SG03 WB outcomes + SG04 Ozon outcomes + separately available SG05 fallback + configured file/PG output.

## Output
`RunPlan` and complete `RunResultSet` keyed by `(marketplace, sku, city)`.

Required persisted common fields:
- run_id;
- timestamp;
- marketplace;
- sku/product identifier;
- city;
- price;
- status/error.

WB additionally: stock quantity/availability.

## Acceptance
Matrix planned before network execution; terminal count equals planned count; missing/duplicate/unexpected outcomes explicit; failures persist as rows; file and PostgreSQL preserve required semantics; WB stock survives; one run_id across targets; no-stdin scheduler-ready primary invocation; repeated runs have distinct identities and bounded/city-correct resources; no automatic SG05 fallback.

## Verdict
`SEMANTIC_COMPILE_PASS`.

---

# SG -> G01 reverse composition

```text
SG01 ProductSet/CitySet
  -> SG02 ProxyContext
       -> SG03 WB price+stock outcomes
       -> SG04 new Ozon proxy-first outcomes
SG05 current personalized-authenticated fallback remains separately reachable
SG01+SG02+SG03+SG04 -> SG06 RunPlan/accounting/persistence/noninteractive run
All six SG outputs -> G01
```

G01 acceptance mapping:
- A01 autonomy -> SG01+SG02+SG03+SG04+SG05 separation+SG06;
- A02 products file/DB -> SG01;
- A03 cities file/DB -> SG01;
- A04 minimal city/proxy contract -> SG01+SG02;
- A05 WB price -> SG03;
- A06 WB stock -> SG03, persisted by SG06;
- A07 Ozon price -> SG04;
- A08 optional wb_dest -> SG01+SG03;
- A09 legacy fallback -> SG05 C02;
- A10 failure isolation -> SG02+SG03+SG04+SG06;
- A11 repeated no-manual-region operation -> SG04+SG05 separation+SG06;
- A12 complete matrix -> SG06.

No G01 output or automatic-fail condition is orphaned.

## Current global verdict

**`SEMANTIC_COMPILE_PASS (WHOLE G01 PROPOSED GENERATION)`**.

Execution may now begin in dependency order. Runtime evidence gates remain authoritative and can force structural repair/recompilation before implementation acceptance.