# G01.SG04 semantic compilation report

Parent: Issue #34
Planning branch: `brain/g01-regional-monitor-plan`

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_CONTEXT_PROBE_REQUIRED)`

This verdict means the Prompt→Task→Stage→Process→SG04 structure is compositionally sufficient. It does **not** claim that current live Ozon behavior has already proven automatic requested-city binding. Runtime evidence is explicitly owned by PR01.

## Current-code findings used by the virtual execution

1. `warm_browser.warm_region()` currently creates a fresh browser profile, asks the user to log in, select/confirm a pickup point, waits for a price, then saves `cookies.json`.
2. `ozon.fetch_price()` requires a supplied cookie list, loads those cookies into `curl_cffi` Session/direct calls, warms the homepage and then fetches the product.
3. Current broad exceptions are printed and the final failure falls back to `{'error':'403'}`, so proxy/session/anti-bot/other failures are not reliably distinguished.
4. Existing `parse_price()` already targets the requested product's `webPrice` state, which is a useful semantic boundary worth preserving rather than replacing with generic price scraping.
5. Ozon's public consumer surfaces expose delivery-address/PVZ context, so proxy IP alone must not be treated as proof of effective requested city without runtime evidence.

## Virtual Prompt execution

### PR01 evidence/contract
Expected result: either (a) fresh proxy-bound Ozon session evidence proves proxy-only or automatic bootstrap/context signals sufficient to verify requested city, or (b) explicit `OZON_CONTEXT_CONTRACT_UNPROVEN` / `OZON_REGION_CONTEXT_UNPROVEN`. No guessing allowed.

### PR02 automatic context
Expected result: a fresh in-memory `OzonContext` created only through SG02 ProxyContext, with automatically issued session state and bounded refresh/rebootstrap. Verified city status is mandatory for successful regional observation.

### PR03 parser/outcomes
Expected result: preserve requested-product `webPrice` parsing; separate transport, context, session/anti-bot and semantic no-price failures; stop broad collapse to `403`.

### PR04 collector/closure
Expected result: each requested Ozon SKU × city produces one typed outcome; primary path neither reads manually warmed `cookies.json` nor launches browser; repeated run can recreate/refresh context automatically.

## Reverse composition

- PR01 supplies evidence-backed current Ozon regional/session contract.
- PR02 supplies autonomous city-bound verified OzonContext.
- PR03 supplies requested-SKU price semantics and explicit failure classes.
- PR04 supplies product×city accounting and first/repeat-run no-manual-warm evidence.

Composition satisfies Issue #34 and contributes to G01:
- A01 autonomous primary operation;
- A07 Ozon regional price;
- A10 failure isolation;
- A11 repeated operation without manual regional authorization;
- A12 complete-matrix Ozon contribution.

## Required runtime gates

### Gate R1 — Fresh-session contract
PR01.ST01 must start without legacy profile/cookies and establish what current Ozon actually requires. Failure verdict: `OZON_CONTEXT_CONTRACT_UNPROVEN`.

### Gate R2 — Requested-city verification
PR01.ST02/PR02.ST02 must define and prove a signal sufficient to bind effective Ozon context to requested `city`. Proxy geolocation alone is not automatically accepted. Failure verdict: `OZON_REGION_CONTEXT_UNPROVEN`.

If either runtime gate fails, implementation may not fake SG04 PASS. If satisfying R2 genuinely requires a new user-supplied city field, the correct action is canonical G01/SG01 contract repair followed by recompilation, not hidden Prompt widening.

## Scope boundaries preserved
- SG02 owns proxy/auth transport.
- SG03 owns WB.
- SG04 owns automatic Ozon regional/session context and price semantics.
- SG05 owns preservation/exposure of the old browser-cookie fallback.
- SG06 owns persistence, complete run orchestration and scheduler-ready operation.

## Global state
Implementation remains blocked until SG05 + SG06 are vertically compiled and the full SG01–SG06 contour is reverse-compiled to G01.