# G01.SG04 — Ozon Proxy-First Regional Price — repaired C02

Parent Goal: G01 / Issue #30
Parent Subgoal: Issue #34
Active planning cycle: `C02.I01`
Status: proposed vertical planning; implementation blocked until full G01 compile PASS.

## Repair reason
C01 incorrectly equated `Selenium/Chrome` with manual legacy behavior and prohibited browser use in the primary path. The corrected contract distinguishes **engine technology** from **human interaction**:

- `curl_cffi` may be used autonomously;
- hidden/headless Selenium/Chrome may be used autonomously;
- either may establish/refresh Ozon session/location context if runtime evidence supports it;
- **human login, manual city/PVZ selection, Enter prompts, manual captcha solving and manually maintained per-city profiles remain forbidden in primary** and belong only to SG05 explicit legacy fallback/support.

C01 Prompt files are retained as immutable history. C02 Prompt files are the active repaired generation.

## Subgoal contract

### Purpose
Replace routine manually warmed Ozon city profiles/cookies with an autonomous proxy-first Ozon path. If Ozon requires a real browser to establish usable session/location state, the primary path may use hidden/headless Selenium/Chrome automatically through the same city ProxyContext.

### Input
- accepted SG01 Ozon `ProductSet` subset;
- accepted SG01 `CityRecord`: `city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`;
- accepted SG02 `ProxyContext` as the single proxy authority plus existing HTTP adapters;
- current Ozon product URL / `webPrice` behavior as runtime evidence target.

### Output
For every requested `ozon sku × city`, one typed outcome containing city/product identity and either an evidenced requested-city price or explicit failure. The normal path requires no manually prepared profile/cookie file and zero human browser actions. Hidden/headless browser execution is allowed when automatic and proxy-bound.

### Acceptance
- every primary Ozon network path derives proxy routing/authentication from selected-city SG02 `ProxyContext`;
- no manually pre-warmed `cookies.json` or profile is a prerequisite;
- any required cookies/session/location context are created automatically by the accepted engine strategy;
- the engine may be `curl_cffi`, hidden/headless Selenium/Chrome, or a bounded evidenced combination;
- no direct-network fallback when ProxyContext is supplied;
- no human login, manual city/PVZ selection, Enter prompt, visible-window prerequisite or human captcha solve;
- effective Ozon regional context is verified sufficiently to prevent a price for unknown/wrong city;
- price parsing remains tied to requested-product `webPrice` state;
- transport/browser/context/session/semantic failures remain explicit;
- repeated runs can recreate/refresh context automatically, including hidden browser lifecycle when needed;
- no additional mandatory CityRecord field unless runtime evidence forces canonical contract repair.

## Dependency/ownership boundary
- SG02 owns canonical ProxyContext and current HTTP transport adapters. SG04 may adapt that same ProxyContext into browser-engine settings but may not invent a second proxy source of truth.
- SG04 owns autonomous Ozon context engine, requested-city verification and price semantics.
- SG05 owns visible/manual legacy profile-cookie/browser fallback and operator maintenance tools. **Selenium itself is not SG05 ownership.**
- SG06 owns persistence, matrix orchestration and scheduler-ready run.

---

# PR01 — Current Ozon regional/session evidence and autonomous-engine contract

## Purpose
Determine from current runtime evidence which automatic engine strategy can obtain requested-city Ozon context without manually warmed profiles.

### ST01 / T01 — Capture fresh-session proxy-first Ozon behavior
Active Prompt: `prompts/work/G01-SG04/PR01-ST01-T01-C02.I01.md`

Input: representative Ozon SKUs + city proxies + SG02 ProxyContext.

Output:
- sanitized evidence from no-legacy state for `curl_cffi` and, where needed, automatic hidden/headless Selenium/Chrome;
- observed cookies/headers/browser/session/location signals;
- proof or failure of browser ProxyContext binding;
- blocked/challenge/no-price cases;
- no credentials/tokens.

Acceptance:
- probes start without legacy `cookies.json`/prepared profile;
- HTTP and browser probes use the same city ProxyContext authority;
- hidden browser requires zero human interaction;
- evidence identifies which engine/sequence is sufficient or explicitly fails closed;
- proxy IP alone is not accepted as requested-city proof.

Failure verdicts: `OZON_CONTEXT_CONTRACT_UNPROVEN`, `OZON_BROWSER_PROXY_BINDING_UNPROVEN`.

### ST02 / T01 — Define evidenced autonomous engine/bootstrap and city-verification contract
Active Prompt: `prompts/work/G01-SG04/PR01-ST02-T01-C02.I01.md`

Input: accepted C02 ST01 evidence.

Output: one deterministic contract defining:
- accepted engine strategy: `curl_cffi`, hidden Selenium/Chrome, or bounded combination;
- evidenced engine order/selection rule without assuming HTTP-first/browser-first;
- automatic state that may be created/transferred between engines;
- exact requested-city verification signal;
- fail-closed engine/context verdicts.

Acceptance:
- hidden browser is allowed; human browser work is forbidden;
- every engine consumes the same ProxyContext authority;
- no manual login/PVZ/profile prerequisite;
- no hidden mandatory CityRecord field;
- wrong/unverified city never succeeds.

---

# PR02 — Automatic proxy-bound Ozon context engine

## Purpose
Implement the accepted C02 autonomous engine strategy and produce a reusable verified `OzonContext` for one CityRecord.

### ST01 / T01 — Build autonomous OzonContext through ProxyContext
Active Prompt: `prompts/work/G01-SG04/PR02-ST01-T01-C02.I01.md`

Input: accepted PR01 C02 engine contract + CityRecord + SG02 ProxyContext/interfaces.

Output: `OzonContext` containing safe city identity, engine provenance, automatically created session/browser state and typed bootstrap status.

Acceptance:
- no legacy `ozon_profile_dir`/`cookies.json` prerequisite;
- `curl_cffi` uses SG02 adapter;
- hidden/headless Selenium/Chrome, when required, receives proxy config derived only from the same ProxyContext;
- inability to prove browser proxy binding fails `OZON_BROWSER_PROXY_BINDING_UNPROVEN` rather than going direct;
- no human interaction;
- browser/driver lifetime, retries and timeouts bounded; child processes cleaned up;
- automatic browser cookies may be reused/transferred only when evidenced.

### ST02 / T01 — Verify city context and support autonomous refresh/rebootstrap
Active Prompt: `prompts/work/G01-SG04/PR02-ST02-T01-C02.I01.md`

Input: fresh/reused C02 OzonContext + accepted verification rule.

Output:
- verified context bound to requested city or typed mismatch/unproven failure;
- bounded automatic refresh/rebootstrap across accepted engine strategy;
- repeat-run behavior with zero human action.

Acceptance:
- wrong/unverifiable city never succeeds;
- every refresh remains on same CityRecord ProxyContext, including browser instances;
- challenge requiring human action becomes typed primary failure;
- no direct networking, city migration or implicit SG05 fallback;
- browser processes/state cleaned up deterministically.

---

# PR03 — Ozon regional price parsing and semantic outcomes

## Purpose
Keep price semantics independent of the autonomous engine that produced accepted content/state.

### ST01 / T01 — Validate engine-neutral requested-product webPrice parsing
Active Prompt: `prompts/work/G01-SG04/PR03-ST01-T01-C02.I01.md`

Input: sanitized successful product content/state under verified C02 OzonContext.

Output: deterministic requested-SKU price fields or explicit semantic failure.

Acceptance:
- equivalent accepted HTTP/browser content yields equivalent semantic result;
- requested-product `webPrice` remains authority;
- no generic page-wide ₽ scraping;
- no networking/browser control inside parser.

### ST02 / T01 — Classify Ozon transport/browser/context/semantic failures
Active Prompt: `prompts/work/G01-SG04/PR03-ST02-T01-C02.I01.md`

Input: SG02 transport facts where applicable + hidden-browser outcome where applicable + context verification + parser output.

Output: typed per-SKU outcome distinguishing success, proxy/auth/connect/timeout/HTTP, browser startup/proxy-binding/navigation/lifecycle, context mismatch/unproven, anti-bot/session/human-action-required, no-price/malformed page and unexpected parser failure.

Acceptance:
- broad failures do not collapse into synthetic `403`;
- browser proxy-binding failure explicit;
- human-action-required challenge explicit, not waiting state;
- requested SKU/city retained;
- no failure looks like valid zero/empty price.

---

# PR04 — Ozon collector integration and SG04 closure

## Purpose
Bind ProductSet + CitySet + SG02 + repaired autonomous C02 OzonContext + parser/outcomes into the primary collector and prove autonomous repeated operation.

### ST01 / T01 — Integrate autonomous proxy-first Ozon product-city observations
Active Prompt: `prompts/work/G01-SG04/PR04-ST01-T01-C02.I01.md`

Input: Ozon ProductSet subset + CitySet + accepted C02 PR02/PR03 interfaces.

Output: one typed outcome for each requested `ozon sku × city`, with regional price on success or explicit failure.

Acceptance:
- collector requires no manually prepared profile/cookies;
- each city uses its own ProxyContext/OzonContext;
- accepted engine may automatically use hidden/headless Selenium/Chrome;
- hidden browser does not imply SG05 fallback;
- legacy `load_cookies`, `warm_region`, `browser_fetch_prices` are not primary prerequisites or automatic manual repair;
- challenges requiring humans remain explicit failure and do not auto-cross into SG05;
- siblings survive individual failures.

### ST02 / T01 — Prove no-human-work repeated-run contract and reverse assembly
Active Prompt: `prompts/work/G01-SG04/PR04-ST02-T01-C02.I01.md`

Input: all accepted SG04 C02 outputs/evidence.

Output: acceptance/evidence map and reverse composition `C02 Prompt → Task → Stage → Process → SG04 → G01 contribution`.

PASS requires:
- fresh first run begins without legacy cookies/profile and can reach a verified-city price or explicit typed failure through accepted autonomous engine;
- hidden browser, when used, is proxy-bound and requires zero human action;
- repeated run can reuse/rebootstrap/refresh automatically;
- wrong/unverified city cannot succeed;
- human-action-required challenges remain primary failures;
- SG05 remains explicit manual fallback only;
- no SG06 scope absorption.

Fail-closed verdicts:
- `OZON_CONTEXT_CONTRACT_UNPROVEN`;
- `OZON_BROWSER_PROXY_BINDING_UNPROVEN`;
- `OZON_REGION_CONTEXT_UNPROVEN`;
- `STRUCTURAL_REPAIR_REQUIRED`.

---

# Reverse composition check — C02

PR01 produces evidence-backed engine/regional semantics.
PR02 produces an autonomous proxy-bound, optionally hidden-browser-backed, verified OzonContext.
PR03 turns engine-neutral accepted content into typed price outcomes.
PR04 accounts for every requested Ozon product-city unit and proves no-human-work repeatability.

The composition satisfies SG04 while preserving SG02 as ProxyContext authority, SG05 as **manual/visible legacy** reserve ownership and SG06 as orchestration/persistence owner.

SG04 contributes to G01 A01, A07, A10, A11 and A12. Full G01 PASS remains blocked until SG06 and final whole-contour compilation.