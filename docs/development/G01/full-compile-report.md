# G01 Whole-Contour Semantic / Virtual Compilation Report

Canonical Goal: Issue #30
Planning PR: #37
Planning branch: `brain/g01-regional-monitor-plan`

## Final proposed-generation verdict

`SEMANTIC_COMPILE_PASS (WHOLE G01 PROPOSED GENERATION)`

The active Prompt generations for SG01–SG06 reverse-compose into the complete G01 contract with no uncovered parent output, no unresolved cross-SG authority contradiction, and no lifecycle/write-scope conflict that cannot be deterministically serialized.

This verdict **authorizes execution of the planned development contour**, beginning with its evidence/implementation Tasks. It does **not** claim runtime marketplace/desktop/PostgreSQL acceptance has already passed and does not itself authorize merge of implementation results. Point-of-use runtime gates remain fail-closed.

---

# 1. Active generation inventory

Only active generations participate in this compile. Superseded Prompt files remain immutable history but are not executable authority.

## SG01 — Dynamic Products and Cities Input
- Processes: #38–#40
- Tasks: #41–#46
- Active Prompts: 6 × `C01.I01`
- Vertical verdict: PASS.

## SG02 — Proxy-First Regional Transport
- Processes: #47–#49
- Tasks: #50–#55
- Active Prompts:
  - #50–#53: `C01.I01`
  - #54–#55: repaired `C02.I01`
- Repair: `docs/development/G01/SG02/C02-repair.md`
- Vertical verdict after repair: PASS.

## SG03 — Wildberries Regional Price and Stock
- Processes: #56–#59
- Tasks: #60–#66
- Active Prompts: 7 × `C01.I01`
- Vertical verdict: PASS with runtime WB stock evidence gate.

## SG04 — Ozon Proxy-First Regional Price
- Processes: #67–#70
- Tasks: #71–#78
- Active Prompts: 8 × `C02.I01`
- C01 superseded because it incorrectly prohibited Selenium/Chrome rather than human interaction.
- Vertical verdict: PASS with runtime engine/proxy-binding/city-context gates.

## SG05 — Legacy Regional Fallback Preservation
- Processes: #79–#81
- Tasks: #82–#87
- Active Prompts: 6 × `C02.I01`
- C01 superseded because it did not make personalized authenticated legacy Ozon cookies/tokens an explicit compatibility invariant.
- Vertical verdict: PASS with authenticated desktop smoke gate.

## SG06 — Complete Matrix Run, Persistence and Autonomous Operation
- Processes: #88–#91
- Tasks: #92–#101
- Active Prompts: 10 × `C01.I01`
- Vertical verdict: PASS.

### Active Prompt total

`6 + 6 + 7 + 8 + 6 + 10 = 43 active Prompts`.

---

# 2. Whole virtual assembly

```text
SG01 ProductSet + CitySet
        |
        v
SG02 one city-bound ProxyContext authority
        |
        +--------------------+
        |                    |
        v                    v
SG03 WB typed outcomes     SG04 Ozon typed outcomes
price + stock             new proxy-first context/price
optional wb_dest          curl_cffi and/or hidden browser
        |                    |
        +---------+----------+
                  |
                  v
SG06 RunPlan -> primary execution -> exact reconciliation
                  |
                  v
           canonical RunResultSet
                  |
             +----+----+
             |         |
             v         v
           file       PostgreSQL

SG05 current personalized-authenticated browser/profile/cookie
fallback remains separately and explicitly reachable
and is never an implicit prerequisite/repair of the primary chain.
```

Reverse result: all children assemble into G01; SG05 contributes directly to G01 fallback preservation rather than becoming a hidden SG06 primary dependency.

---

# 3. Cross-SG repairs found during compilation

## Repair R1 — SG04 C02: hidden Selenium is allowed in autonomous primary
Earlier SG04 C01 incorrectly equated Selenium/Chrome with manual fallback. Repaired invariant:
- automatic hidden/headless Selenium/Chrome may be SG04 primary;
- human login/PVZ/captcha/profile maintenance is SG05 fallback/support.

Resolved before SG06.

## Repair R2 — SG05 C02: current fallback requires personalized authenticated cookies
The current working Ozon reserve path depends on user-authenticated personalized cookies/tokens. They are mandatory compatibility material for SG05 fallback, not generic cookies and not a requirement of new SG04 proxy-first primary.

Resolved before SG06.

## Repair R3 — SG02 C02: ProxyContext authority is library-neutral
Whole-G01 compile found stale SG02 C01 wording requiring every Ozon network call to transit through curl_cffi. This contradicted repaired SG04 hidden-browser primary.

Repaired invariant:
- SG02 owns one canonical ProxyContext authority and HTTP adapters;
- current Ozon HTTP uses curl_cffi adapter;
- SG04 hidden browser may adapt the **same** ProxyContext into browser settings;
- browser is not required to transit curl_cffi;
- no second raw proxy credential authority and no silent direct fallback.

Tasks #54/#55 now use active C02 Prompts.

After R3, cross-SG authority compilation PASS.

---

# 4. G01 Acceptance reverse mapping

## G01.A01 — autonomous repeated monitoring without manual city switching
Produced by:
- SG01 source-neutral CitySet;
- SG02 non-interactive proxy authority;
- SG03 no manual WB dest prerequisite;
- SG04 zero-human proxy-first Ozon context;
- SG05 proving legacy is not a primary prerequisite;
- SG06 scheduler-ready/repeat lifecycle.

PASS by composition.

## G01.A02 — products dynamic from file/DB
SG01 PR01 + closure.

PASS.

## G01.A03 — cities dynamic from file/DB
SG01 PR02 + closure.

PASS.

## G01.A04 — minimum city/proxy contract sufficient
SG01 defines exactly:
`city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`.

SG02 consumes it without extra required transport field. SG03 accepts missing wb_dest. SG04 runtime gates must trigger canonical repair rather than silently adding fields if current Ozon proves more city semantics are genuinely necessary.

PASS as proposed contract, fail-closed at runtime evidence.

## G01.A05 — WB regional price
SG03 PR02/PR03/PR04.

PASS by proposed composition.

## G01.A06 — WB regional stock/availability
SG03 PR01 evidence -> PR03 parser -> PR04 collector -> SG06 persistence.

PASS structurally; runtime gate #60 must first prove actual current endpoint stock semantics. No guessed schema allowed.

## G01.A07 — Ozon regional price
SG02 ProxyContext -> SG04 C02 autonomous engine/context -> engine-neutral webPrice parser -> SG06 accounting/persistence.

PASS structurally; SG04 runtime engine/proxy-binding/requested-city gates remain mandatory.

## G01.A08 — missing wb_dest valid
SG01 accepts nullable/absent wb_dest; SG02 ignores it for transport; SG03 omits dest instead of aborting; SG05 manual dest remains optional support; SG06 does not revalidate it as required.

PASS.

## G01.A09 — legacy cookies/profile fallback preserved
SG05 C02 preserves current explicitly invoked personalized-authenticated Ozon profile/cookie/browser mechanism plus operator refresh/support path; primary SG04/SG06 never requires or auto-enters it.

PASS structurally; authenticated desktop smoke remains runtime evidence.

## G01.A10 — errors isolated and not valid values
SG02 typed transport failures -> SG03/SG04 typed marketplace failures -> SG06 precomputed RunPlan/reconciliation -> canonical failure rows in file/PG.

Current empty/error filtering and `is_available=True` defaults are explicitly removed by SG06 contracts.

PASS.

## G01.A11 — repeated cycle needs no manual regional setup
SG04 repeated automatic context refresh/rebootstrap + SG05 separation + SG06 no-stdin/two-run lifecycle.

PASS structurally; runtime Ozon zero-human evidence required.

## G01.A12 — complete Products × Cities × Marketplaces accounting
SG06 #92 creates expected matrix before network calls; #93 guarantees one terminal row per planned key; #100 proves file/PG parity to canonical RunResultSet.

PASS.

No G01 acceptance clause is orphaned.

---

# 5. Parent Output Contract assembly

G01 minimum output fields:
- timestamp -> SG06 RunResult;
- marketplace -> SG03/SG04 identity preserved by SG06;
- product identifier -> SG01 plan identity preserved through SG06;
- city -> SG01 CityRecord/RunPlan preserved through SG06;
- price -> SG03/SG04 success semantics;
- status/error -> SG02/SG03/SG04 typed failures normalized by SG06;
- WB stock/availability -> SG03, persisted by SG06.

Every planned marketplace/product/city unit is created in RunPlan before collection, so output completeness is no longer inferred from successful collector rows.

PASS.

---

# 6. Authority compilation

## Product/city authority
SG01 only.
No later SG may replace primary CitySet with legacy config.regions.

PASS.

## Proxy authority
SG02 ProxyContext only.
- requests/curl_cffi adapters consume it;
- SG04 hidden-browser adaptation derives from it;
- SG06 selects it per city;
- no direct fallback under supplied context.

PASS after SG02 C02 repair.

## WB semantic authority
SG03 only for price/stock/dest semantics.
SG06 may account/persist but not reinterpret.

PASS.

## Ozon primary semantic authority
SG04 C02 only for engine selection, technical session state, hidden browser, requested-city verification and price semantics.
SG05 authenticated cookies do not leak into this authority.

PASS.

## Legacy authenticated fallback authority
SG05 C02 only.
Current personalized authenticated cookies/tokens are secret runtime fallback material. SG06 does not auto-enter it.

PASS.

## Matrix/run authority
SG06 RunPlan + RunResult only.
Collector-return row count cannot become expected-count authority.

PASS.

---

# 7. Lifecycle compilation

## CityRecord / ProxyContext
CityRecord exists before network execution. ProxyContext is constructed/reused only for that city and remains valid for SG03/SG04 request lifetime. SG06 cannot rebind it to another city.

PASS.

## SG03 WB stock evidence
#60 evidence lifetime precedes stock normalization/parser Tasks. If endpoint evidence cannot prove stock, downstream SG03 stock implementation stops with `WB_STOCK_CONTRACT_UNPROVEN`; SG06 cannot manufacture stock later.

PASS fail-closed.

## SG04 OzonContext / hidden browser
Engine/context evidence precedes construction/use. Browser proxy binding and requested-city verification precede successful price. Browser resources are bounded; SG06 repeat lifecycle verifies no wrong-city/cross-run leakage.

PASS fail-closed.

## SG05 personalized authenticated profile
Exists only when explicit fallback is intentionally used. It is not created/required by primary RunPlan. Expired/rejected legacy auth produces explicit fallback maintenance/failure and cannot force primary startup dependency.

PASS.

## run_id / RunPlan / persistence
run_id is allocated before execution and lives through reconciliation and both persistence targets. Repeated runs allocate distinct run_id; previous rows remain immutable under their original run identity.

PASS.

No parent postcondition destroys a capability required by a downstream child.

---

# 8. Write-scope / merge-order compilation

Some Tasks may touch shared implementation files, so execution must respect semantic dependencies and serialize overlapping write scopes.

Mandatory rules:
1. SG01 DB input changes precede SG06 ParserDB result-schema changes; do not concurrently edit `db.py` from #44 and #96.
2. SG02 transport integration precedes SG03/SG04 collector integration.
3. SG03 #65 and SG04 #77 may implement marketplace-specific collector boundaries, but **final unified primary orchestration belongs to SG06 #97**.
4. If SG03 #65 and SG04 #77 both need the same shared runner file, serialize/merge them rather than parallel-write the file.
5. SG06 #97/#98 consume accepted marketplace interfaces; they must not duplicate/replace marketplace parser implementations.
6. Planning/Prompt artifacts do not authorize concurrent Workers to overwrite one another's accepted interfaces.

With serialization, no unavoidable write conflict remains.

PASS.

---

# 9. Proposed execution dependency contour

High-level order:

```text
SG01 inputs
  -> SG02 transport C02 closure
       -> SG03 WB evidence/implementation
       -> SG04 Ozon C02 evidence/implementation
       -> SG05 C02 fallback preservation (separate, explicit)
  -> SG06 complete run/persistence/entrypoint
  -> runtime acceptance evidence / reviews
```

SG03 and SG04 evidence/parser work may proceed independently after SG02, but shared-file collector integration must be serialized as above.

Within SG06:
- #92 RunPlan contract;
- #93 reconciliation and #94 normalization can be implemented against fixtures/interfaces;
- #95/#96 storage after #94;
- #97 final primary collector composition after accepted SG03/SG04;
- #98 non-interactive entrypoint after runner/storage interfaces exist;
- #99 repeat lifecycle;
- #100 mixed matrix/file/PG proof;
- #101 SG06 closure.

---

# 10. Runtime gates intentionally deferred to execution

Semantic compilation does not fabricate live external evidence.

Mandatory execution-time gates include:

### WB
- #60: current consumer endpoint stock schema/semantics.
- Failure: `WB_STOCK_CONTRACT_UNPROVEN` -> stop affected downstream work / repair contract if necessary.

### Ozon new primary
- #71/#72: autonomous engine strategy, hidden-browser ProxyContext binding if used, requested-city verification.
- Failures include `OZON_CONTEXT_CONTRACT_UNPROVEN`, `OZON_BROWSER_PROXY_BINDING_UNPROVEN`, `OZON_REGION_CONTEXT_UNPROVEN`.

### Legacy fallback
- #86/#87: real visible desktop smoke with runtime-local personalized authenticated profile/cookies, without secret capture.
- Failure includes `LEGACY_AUTH_COOKIE_SEMANTICS_LOST`.

### PostgreSQL / full run
- #96/#100: disposable/live PostgreSQL migration/round-trip and complete mixed-run parity evidence.
- Lack of environment must be reported as missing runtime evidence, never synthetic PASS.

Any runtime finding proving a canonical contract wrong triggers structural repair/recompilation. Repeated Prompt widening is not allowed.

---

# 11. Automatic G01 FAIL reverse check

Each Goal-level fail condition has an explicit preventing child contract:
- manual city/cookie routine in primary -> SG04/SG05/SG06 gates;
- hardcoded products/cities/proxies -> SG01;
- WB stock absent -> SG03 evidence gate;
- Ozon not proxy-first -> SG02/SG04;
- wb_dest required -> SG01/SG03;
- fallback broken -> SG05;
- result not attributable -> SG06 RunPlan/RunResult;
- errors look like real data -> SG02/SG03/SG04/SG06;
- unjustified city fields -> SG01 + runtime structural-stop rules.

No automatic-fail condition is left without an enforcement path.

PASS.

---

# 12. Final reverse compile

```text
43 active Prompts
    -> Tasks
    -> Stages
    -> Processes
    -> SG01 + SG02(C02 repaired) + SG03 + SG04(C02) + SG05(C02) + SG06
    -> G01 Goal contract
```

## Final verdict

**SEMANTIC_COMPILE_PASS — WHOLE G01 PROPOSED GENERATION.**

The planning contour is now structurally sufficient to begin controlled implementation execution. Runtime evidence gates remain authoritative and may stop/repair the contour before a marketplace Task or Goal can receive implementation acceptance.

No parser implementation has been performed by this planning PR.