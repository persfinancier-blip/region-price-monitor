# G01.SG04 — Ozon Proxy-First Regional Price

Parent Goal: G01 / Issue #30
Parent Subgoal: Issue #34
Status: proposed vertical planning; implementation blocked until full G01 compile PASS.

## Subgoal contract

### Purpose
Replace routine manually warmed Ozon city profiles/cookies with an autonomous proxy-first Ozon path. If Ozon needs session/context beyond the city proxy, that context must be bootstrapped and verified automatically.

### Input
- accepted SG01 `ProductSet` Ozon subset;
- accepted SG01 `CityRecord` with `city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest` (irrelevant to Ozon);
- accepted SG02 `ProxyContext` + curl_cffi transport adapter;
- current Ozon product URL / `webPrice` parsing behavior as implementation evidence target.

### Output
For every requested `ozon sku × city`, one typed outcome containing city/product identity and either an endpoint-evidenced regional price or an explicit failure. The normal path requires no manually prepared Ozon browser profile/cookie file and repeated runs require no browser action.

### Acceptance
- every normal-path Ozon network call uses the selected city `ProxyContext`;
- no manually pre-warmed `cookies.json` is a prerequisite of normal operation;
- any required cookies/session/location context are created automatically;
- the effective Ozon regional context is verified sufficiently to prevent returning a price for an unknown/wrong city;
- price parsing remains tied to the requested product `webPrice` state rather than arbitrary ₽ text;
- transport, anti-bot/session, context mismatch and semantic no-price failures remain distinct;
- repeated runs can recreate or refresh required session/context without human browser action;
- no additional mandatory CityRecord field is introduced unless runtime evidence proves G01 cannot be met without canonical contract repair.

## Dependency boundary
SG04 consumes SG01 + SG02. It does not own proxy construction, WB behavior, legacy fallback preservation, persistence or scheduling.

---

# PR01 — Current Ozon regional/session evidence and context contract

## Purpose
Determine, from current live behavior and sanitized fixtures, what a fresh proxy-bound Ozon session needs in order to obtain a product price for the requested city and how the effective region can be verified.

### ST01 / T01 — Capture fresh-session proxy-first Ozon behavior
Prompt: `prompts/work/G01-SG04/PR01-ST01-T01-C01-I01.md`

Input: representative Ozon SKUs + at least representative city proxy configurations + SG02 transport.

Output:
- sanitized HTTP/session evidence from a fresh state with no manually warmed profile;
- observed cookies/headers/page-state/location signals required by successful product requests;
- observed blocked/challenge/no-price cases;
- no committed credentials or account tokens.

Acceptance:
- probes start without legacy `cookies.json`;
- all calls use city ProxyContext;
- observed facts, not remembered Ozon behavior, are recorded;
- evidence includes enough regional/location signal to attempt city-binding proof or explicitly says it cannot be proven.

Failure: evidence unavailable -> typed `OZON_CONTEXT_CONTRACT_UNPROVEN`; downstream context implementation must not guess.

### ST02 / T01 — Define evidenced Ozon regional bootstrap and verification contract
Prompt: `prompts/work/G01-SG04/PR01-ST02-T01-C01-I01.md`

Input: accepted ST01 evidence.

Output: one deterministic contract stating:
- whether proxy-only fresh session is sufficient or additional automatic bootstrap is required;
- exact observed bootstrap state that may be created automatically;
- exact evidence used to accept/reject effective city binding;
- typed `OZON_REGION_CONTEXT_UNPROVEN` when requested city cannot be verified from the minimum G01 CityRecord/current Ozon behavior.

Acceptance:
- no manual login/PVZ selection is normalized into the primary path;
- no hidden new mandatory CityRecord field;
- no assumption that proxy geolocation alone equals Ozon effective delivery context;
- any required additional user field triggers canonical Goal/Subgoal contract review rather than Prompt widening.

---

# PR02 — Automatic proxy-bound Ozon session/context bootstrap

## Purpose
Implement the evidenced fresh-session/bootstrap contract entirely through SG02 transport and produce a reusable, secret-safe OzonContext for one CityRecord.

### ST01 / T01 — Bootstrap fresh Ozon session through ProxyContext
Prompt: `prompts/work/G01-SG04/PR02-ST01-T01-C01-I01.md`

Input: accepted PR01 bootstrap contract + CityRecord + SG02 curl_cffi adapter.

Output: `OzonContext` containing only automatically created in-memory/session state needed by later Ozon requests plus safe city identity/status.

Acceptance:
- starts with no manual profile/cookie file;
- every bootstrap call uses the supplied ProxyContext;
- cookies/session state returned by Ozon may be captured automatically but secrets are not logged;
- anti-bot/HTTP/transport/bootstrap failures are typed;
- no direct-network fallback.

### ST02 / T01 — Verify city context and support autonomous refresh/retry
Prompt: `prompts/work/G01-SG04/PR02-ST02-T01-C01-I01.md`

Input: fresh/reused OzonContext + accepted PR01 verification rule.

Output:
- verified context bound to requested `city`, or explicit context mismatch/unproven failure;
- bounded automatic refresh/rebootstrap behavior for expired/rejected session state;
- repeat-run behavior that requires no browser action.

Acceptance:
- wrong/unverifiable city never becomes successful regional price;
- refresh never silently changes city identity;
- no manual login/PVZ/browser action in primary path;
- no infinite retry loop;
- failure remains typed and secret-free.

---

# PR03 — Ozon regional price parsing and semantic outcomes

## Purpose
Use verified OzonContext to fetch the requested product and preserve the existing high-signal `webPrice` parser while making success/failure classification explicit.

### ST01 / T01 — Validate and preserve requested-product webPrice parsing
Prompt: `prompts/work/G01-SG04/PR03-ST01-T01-C01-I01.md`

Input: sanitized successful product-page fixtures obtained under accepted context.

Output: deterministic parser for requested SKU price fields (`price`, card/regular/original/base where present), currency and availability as evidenced by current `webPrice` state.

Acceptance:
- requested product `webPrice` state remains the semantic source;
- unrelated recommendation/installment ₽ values are not parsed;
- malformed/missing widget is explicit semantic failure;
- no networking or session bootstrap inside parser.

### ST02 / T01 — Classify Ozon transport, context and semantic failures
Prompt: `prompts/work/G01-SG04/PR03-ST02-T01-C01-I01.md`

Input: SG02 TransportOutcome + OzonContext verification state + parser output.

Output: typed per-SKU Ozon outcome distinguishing success, context mismatch/unproven, proxy/auth/connect/timeout/HTTP, anti-bot/session rejection, product/no-price/malformed page and unexpected parser failure.

Acceptance:
- broad exception is not blindly returned as `403`;
- `200_no_price` is not a proxy failure;
- failed unit preserves requested SKU and city;
- no failure becomes a valid-looking zero/empty price.

---

# PR04 — Ozon collector integration and SG04 closure

## Purpose
Bind ProductSet + CitySet + SG02 + automatic OzonContext + parser/outcomes into the actual normal Ozon collector and prove autonomous repeated operation.

### ST01 / T01 — Integrate proxy-first Ozon product-city observations
Prompt: `prompts/work/G01-SG04/PR04-ST01-T01-C01-I01.md`

Input: Ozon ProductSet subset + CitySet + accepted PR02/PR03 interfaces.

Output: one typed outcome for each requested `ozon sku × city`, with regional price on success or explicit failure.

Acceptance:
- collector does not require `ozon_profile_dir`/`cookies.json` in primary path;
- each city creates/uses its own verified ProxyContext/OzonContext;
- one product/city failure does not erase siblings;
- no automatic browser launch in normal path;
- legacy profile path is untouched for SG05 ownership.

### ST02 / T01 — Prove no-manual-warm repeated-run contract and reverse assembly
Prompt: `prompts/work/G01-SG04/PR04-ST02-T01-C01-I01.md`

Input: all SG04 accepted outputs/evidence.

Output: acceptance/evidence map and reverse composition `Prompt → Task → Stage → Process → SG04 → G01 contribution`.

PASS requires:
- fresh first run succeeds for a verified city without manually warmed cookies/profile;
- a repeated run can succeed/rebootstrap/refresh without human action;
- city proxy use and context verification are proven;
- failures are explicit;
- no scope absorption from SG05/SG06.

Fail-closed verdicts:
- `OZON_CONTEXT_CONTRACT_UNPROVEN` — current fresh-session requirements not evidenced;
- `OZON_REGION_CONTEXT_UNPROVEN` — effective requested city cannot be proven with current minimum contract;
- `STRUCTURAL_REPAIR_REQUIRED` — decomposition/task boundary is wrong.

---

# Reverse composition check

PR01 produces evidence-backed regional/session semantics.
PR02 produces an autonomous verified city-bound OzonContext.
PR03 turns verified product responses into typed price outcomes.
PR04 accounts for every requested Ozon product-city unit and proves repeat-run autonomy.

Their composition satisfies SG04 without requiring SG05 legacy fallback or SG06 persistence/scheduler work.

SG04 contributes to G01 A01, A07, A10, A11 and A12. Full G01 PASS remains blocked until SG05, SG06 and final whole-contour compilation pass.