# G01.SG05 Semantic Compile Report — active cycle C02

Parent: Issue #35
Branch: `brain/g01-regional-monitor-plan`

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only; LEGACY_AUTHENTICATED_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`

This verdict authorizes no implementation yet. Full G01 compilation remains blocked until SG06 is vertically compiled and the complete contour is reverse-assembled.

## Corrected semantic boundary

The current working Ozon fallback requires **personalized authenticated cookies/tokens from a user-confirmed Ozon login**. That requirement belongs to SG05 legacy fallback only.

The new SG04 proxy-first mechanism does **not** require these personalized authenticated legacy cookies/profile. Ordinary automatically issued HTTP/browser runtime state in SG04 is a separate concept.

## Current-code findings

1. `cli.main()` currently executes `review_profiles()`, `repair_regions()` and `add_new_regions()` before `run_parsing()`, so legacy preparation is currently coupled to normal startup.
2. `repair_regions()` invokes `warm_region()` when Ozon legacy profile is absent and `get_wb_dest()` when WB dest is absent.
3. `run_parsing()` loads legacy Ozon `cookies.json` and, when curl_cffi fails, automatically invokes `browser_fetch_prices()`.
4. The current Ozon fallback cookies are personalized authenticated user cookies/tokens, not interchangeable anonymous cookies; preserving only generic cookie mechanics would not preserve the working fallback.
5. Current WB path skips a region without `wb_dest`; SG03 owns replacement of that primary behavior.

## Virtual Prompt execution — C02

### PR01
- ST01 inventories all current legacy entrypoints/artifacts and explicitly classifies Ozon cookies/tokens as personalized authenticated secret runtime material.
- ST02 separates new proxy-first primary from the legacy authenticated credential/profile path.
Result: PASS.

### PR02
- ST01 preserves explicit Ozon fallback using existing personalized authenticated profile/cookies; absent/expired/rejected auth fails explicitly and never silently downgrades to anonymous cookies.
- ST02 preserves operator-assisted authenticated `warm_region` profile refresh plus other legacy maintenance tools.
Result: PASS.

### PR03
- ST01 proves primary no-call/no-auth-cookie invariants and explicit authenticated fallback reachability; live visible-browser/authenticated-cookie smoke remains environment-specific and secret-safe.
- ST02 maps all repaired SG05 acceptance clauses back to G01.
Result: PASS with runtime authenticated desktop smoke evidence required at implementation execution.

## Reverse assembly

```text
6 C02 Prompts
  -> 6 Tasks
  -> 6 Stages
  -> PR01 + PR02 + PR03
  -> SG05
  -> G01
```

Coverage:
- G01.A09 fallback preservation: current authenticated browser/profile/cookies mechanism is explicitly preserved.
- G01.A01/A11: new proxy-first primary is independent from legacy authenticated regional preparation.
- G01.A08: manual WB dest remains optional support only.

No SG05 output is required by SG04 primary. No SG05 Task implements SG03/SG04 primary marketplace semantics or SG06 orchestration/persistence.

## Adversarial virtual cases

- Primary Ozon fails -> legacy browser/profile must NOT open/load automatically. PASS by contract.
- No legacy `cookies.json` exists -> new proxy-first primary remains valid; legacy fallback is unavailable until intentionally prepared. PASS.
- Existing authenticated old profile exists -> explicit legacy fallback can still consume it. PASS.
- Worker substitutes anonymous/generated cookies -> `LEGACY_AUTH_COOKIE_SEMANTICS_LOST`; SG05 FAIL. PASS fail-closed.
- Legacy auth expires/is rejected -> explicit fallback maintenance/auth failure; no anonymous downgrade. PASS.
- Real cookie/token values appear in Git/log/result/evidence -> SG05 FAIL. PASS fail-closed.
- `wb_dest` missing -> primary WB remains SG03 responsibility; optional legacy `get_wb_dest` remains reachable. PASS.
- Headless server cannot run visible authenticated smoke -> deterministic separation/reachability can pass planning, but live smoke stays explicit execution gate. PASS.

## Compile boundary

```text
PRIMARY NEW PATH:
proxy-first SG04
no legacy personalized auth-cookie/profile prerequisite

LEGACY CURRENT FALLBACK:
explicit operator invocation
+ user-authenticated Ozon profile
+ personalized cookies/tokens
+ preserved browser/curl_cffi regional flow
```

Fail-closed verdicts:
- `LEGACY_AUTH_COOKIE_SEMANTICS_LOST`
- `PRIMARY_LEGACY_RECOUPLED`
- `LEGACY_FALLBACK_RUNTIME_PROBE_REQUIRED`
- `STRUCTURAL_REPAIR_REQUIRED`
