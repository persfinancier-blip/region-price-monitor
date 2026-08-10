# G01.SG05 Semantic Compile Report

Parent: Issue #35
Branch: `brain/g01-regional-monitor-plan`

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only; LEGACY_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`

This verdict authorizes no implementation yet. Full G01 compilation remains blocked until SG06 is also vertically compiled and the complete contour is reverse-assembled.

## Current-code findings

1. `cli.main()` currently executes `review_profiles()`, `repair_regions()` and `add_new_regions()` before `run_parsing()`. Therefore legacy preparation is currently coupled to normal startup.
2. `repair_regions()` invokes `warm_region()` when Ozon legacy profile is absent and `get_wb_dest()` when WB dest is absent.
3. `run_parsing()` loads Ozon legacy cookies/profile and, when curl_cffi fails, automatically invokes `browser_fetch_prices()`.
4. Current WB path skips a region without `wb_dest`; SG03 owns replacement of that primary behavior.
5. Legacy Ozon browser/profile/cookies tooling is real useful functionality and must not be deleted during SG04 migration.

## Virtual Prompt execution

### PR01
- T01 inventories every current legacy entrypoint/artifact and classifies automatic browser fallback/profile preflight as primary coupling to remove.
- T02 defines explicit operator intent as the gate to interactive legacy work.
Result: PASS.

### PR02
- T01 preserves Ozon legacy profile/cookie/browser capability behind explicit fallback invocation.
- T02 preserves profile maintenance and manual WB dest discovery as explicit operator support tools.
Result: PASS.

### PR03
- T01 proves primary no-call invariants and legacy explicit reachability; browser live smoke is environment-specific but must have a deterministic desktop procedure.
- T02 maps all SG05 acceptance clauses back to G01.
Result: PASS with runtime desktop smoke evidence required when implementation executes on a suitable host.

## Reverse assembly

```text
6 Prompts
  -> 6 Tasks
  -> 6 Stages
  -> PR01 + PR02 + PR03
  -> SG05
  -> G01
```

Coverage:
- G01.A09 fallback preservation: fully produced by SG05.
- G01.A01/A11: SG05 contribution proves no normal/repeated primary dependency on browser/profile/cookie maintenance.
- G01.A08: SG05 preserves manual WB dest discovery only as optional support and does not make `wb_dest` mandatory.

No orphan parent requirement exists at SG05 level. No SG05 Task is required to implement SG03/SG04 primary semantics or SG06 orchestration/persistence.

## Adversarial virtual cases

- Primary Ozon fails -> browser must NOT open automatically; explicit typed failure remains. PASS by contract.
- No `cookies.json` exists -> primary path remains valid; legacy fallback may be unavailable until intentionally prepared. PASS.
- Existing old profile exists -> explicit legacy fallback can still consume it. PASS.
- `wb_dest` missing -> primary WB remains SG03 responsibility; operator may explicitly use legacy `get_wb_dest`, but SG05 cannot force it. PASS.
- Headless server -> primary remains usable; legacy desktop smoke is not falsely claimed to run there. PASS.
- Legacy code becomes unreachable after refactor -> SG05 regression gate fails. PASS fail-closed.
- Automatic fallback policy requested later -> separate contract change; not smuggled into SG05. PASS.

## Compile boundary

SG05 is structurally sufficient only if implementation preserves both independent capabilities:

```text
PRIMARY: autonomous proxy-first, zero interactive legacy prerequisite
LEGACY: explicit operator-invoked browser/profile/cookies reserve path
```

If implementation can only preserve legacy by recoupling it to primary startup, verdict becomes `PRIMARY_LEGACY_RECOUPLED` and decomposition/implementation must be repaired.
