# G01.SG02 — Proxy-First Regional Transport — vertical decomposition

Status: PROPOSED / planning only. No implementation authority until the whole G01 contour compiles.
Parent Goal: G01 / Issue #30
Parent Subgoal: G01.SG02 / Issue #32
Depends semantically on: G01.SG01 `CityRecord` contract.

## 1. Subgoal contract

### Purpose
Provide one minimum authenticated proxy transport boundary for a selected city, usable by both WB (`requests`) and Ozon (`curl_cffi`) without requiring browser/profile preparation inside the transport layer.

### Input contract
`CityRecord` from SG01:
- `city` required;
- `proxy` required;
- `proxy_user` required;
- `proxy_password` required;
- `wb_dest` optional and transport-opaque.

Plus a marketplace request specification supplied by the owning collector.

### Output contract
A city-bound `ProxyContext` plus structured transport outcomes that:
- actually apply proxy authentication;
- are usable by both HTTP stacks already present in the product;
- distinguish successful HTTP response from proxy/auth/connect/timeout/HTTP failure;
- never convert transport failure into an empty valid marketplace result;
- do not expose proxy credentials in ordinary logs, result records, exception summaries or safe representations;
- require no `ozon_profile_dir`, cookies file, browser warm-up or WB `dest` to construct/use the transport itself.

### Explicit ownership boundary
SG02 owns transport only. It does **not** own:
- WB price/stock parsing or optional-`dest` marketplace semantics — SG03;
- Ozon automatic regional/session bootstrap and price semantics — SG04;
- legacy browser/profile fallback — SG05;
- complete matrix orchestration/persistence/scheduler-ready run — SG06.

## 2. Process decomposition

### G01.SG02.PR01 — Authenticated proxy context and safe transport contract
Purpose: turn the minimum SG01 city fields into a reusable authenticated proxy context and typed transport result without adding user-facing fields.

#### Input
Canonical `CityRecord`.

#### Output
`ProxyContext` with:
- authenticated proxy endpoint usable by supported adapters;
- safe/redacted identity for diagnostics;
- city identity without duplicating unrelated marketplace semantics.

Typed `TransportOutcome`/errors sufficient to distinguish at least:
- success;
- proxy authentication/proxy connection failure;
- connection/DNS/TLS transport failure where distinguishable;
- timeout;
- HTTP non-success response;
- unexpected adapter failure.

#### Stage G01.SG02.PR01.ST01 — ProxyContext construction
##### Task G01.SG02.PR01.ST01.T01 — Build authenticated ProxyContext from minimum CityRecord
Input: SG01 CityRecord.
Output: deterministic ProxyContext; if `proxy` has no scheme use one documented default compatible with current HTTP proxy usage; if a supported scheme is already present preserve it. User/password are safely URL-encoded for the transport endpoint. Safe representation contains no secret.
Acceptance:
1. uses only `city`, `proxy`, `proxy_user`, `proxy_password`; `wb_dest` is not required;
2. no new mandatory field;
3. host:port input is accepted;
4. malformed proxy input fails explicitly;
5. credentials containing reserved URL characters are encoded correctly;
6. `repr`/diagnostic/safe label contains no password and no raw authenticated URI.
Evidence: unit fixtures with dummy credentials including reserved characters.
Failure: provider-specific API fields become mandatory; credentials are logged or returned as public result data.
Prompt: `prompts/work/G01-SG02/PR01-ST01-T01-C01-I01.md`.

#### Stage G01.SG02.PR01.ST02 — Structured transport outcome and redaction
##### Task G01.SG02.PR01.ST02.T01 — Define typed transport outcomes and safe errors
Input: adapter success/exception/status facts.
Output: one source-neutral transport outcome/error contract carrying only safe diagnostics and response metadata required by collectors.
Acceptance:
1. failure is not represented as `[]`, `{}` or valid zero/absence;
2. proxy/auth/connect/timeout/HTTP failure remain distinguishable at the minimum useful level;
3. raw credentials/authenticated proxy URLs are redacted from messages;
4. HTTP response body remains available only where explicitly required by a successful/HTTP outcome, without mixing semantic product parsing into transport.
Evidence: error-mapping/redaction tests.
Failure: marketplace semantics leak into transport result or errors collapse into a fake successful empty result.
Prompt: `prompts/work/G01-SG02/PR01-ST02-T01-C01-I01.md`.

### G01.SG02.PR02 — HTTP-stack proxy adapters
Purpose: make the same ProxyContext work with the two libraries already required by the current product.

#### Input
ProxyContext + request specification.

#### Output
Two narrow adapters that consume the same context/result contract while preserving library-specific mechanics internally.

#### Stage G01.SG02.PR02.ST01 — `requests` adapter
##### Task G01.SG02.PR02.ST01.T01 — Route requests traffic through ProxyContext
Input: ProxyContext + method/url/params/headers/timeouts required by caller.
Output: structured TransportOutcome from Python `requests` with authenticated proxy applied to HTTP/HTTPS traffic.
Acceptance:
1. adapter cannot silently make a direct request when a valid ProxyContext was supplied;
2. proxy mapping contains the authenticated endpoint derived from context;
3. timeout/connect/proxy/HTTP outcomes map safely;
4. no credential-bearing exception string is printed directly.
Evidence: mocked request inspection + negative fixtures.
Failure: supplied proxy ignored/bypassed or direct fallback occurs silently.
Prompt: `prompts/work/G01-SG02/PR02-ST01-T01-C01-I01.md`.

#### Stage G01.SG02.PR02.ST02 — `curl_cffi` adapter
##### Task G01.SG02.PR02.ST02.T01 — Route curl_cffi traffic through ProxyContext
Input: ProxyContext + Ozon-compatible request/session specification including impersonation where required by caller.
Output: structured TransportOutcome from `curl_cffi`, preserving current ability to use direct request or caller-owned session while applying the same authenticated proxy context.
Acceptance:
1. same ProxyContext fields as requests adapter;
2. proxy is applied to all network calls made through the adapter;
3. caller may own cookie/session bootstrap later (SG04), but adapter itself requires no profile/cookie file;
4. failures map into the common safe outcome contract;
5. no raw credential exception logging.
Evidence: mocked curl_cffi/session inspection + negative fixtures.
Failure: adapter requires legacy profile/cookies to exist or bypasses proxy for bootstrap calls.
Prompt: `prompts/work/G01-SG02/PR02-ST02-T01-C01-I01.md`.

### G01.SG02.PR03 — Marketplace transport handoff and SG02 closure
Purpose: prove WB and Ozon collector boundaries can consume the shared context without widening SG02 into marketplace semantics.

#### Input
Accepted PR01 contracts and PR02 adapters; current `wb.py` and `ozon.py` call boundaries.

#### Output
One explicit transport handoff used by both collector modules plus deterministic SG02 acceptance evidence.

#### Stage G01.SG02.PR03.ST01 — Collector transport integration boundary
##### Task G01.SG02.PR03.ST01.T01 — Bind WB and Ozon request paths to shared transport
Input: current WB/Ozon network call sites + ProxyContext/adapters.
Output: network calls in both collectors receive/use the shared city-bound transport context; semantic price/stock/cookie/bootstrap behavior is otherwise preserved for its owning SG.
Acceptance:
1. WB request path no longer constructs/accepts an unrelated raw proxy mechanism as semantic authority;
2. Ozon request path uses the same ProxyContext for every call, including any caller-owned bootstrap call routed through the adapter;
3. no direct-network fallback when a proxy context is supplied;
4. this Task does not claim Ozon cookie removal or WB optional-dest completion;
5. existing parser semantics remain outside the transport adapter.
Evidence: collector-boundary tests proving proxy binding for both stacks.
Failure: integration forces legacy profile/dest preparation into ProxyContext or widens into SG03/SG04 behavior.
Prompt: `prompts/work/G01-SG02/PR03-ST01-T01-C01-I01.md`.

#### Stage G01.SG02.PR03.ST02 — SG02 compile/acceptance gate
##### Task G01.SG02.PR03.ST02.T01 — Prove proxy-first transport contract
Input: all SG02 implementation/evidence.
Output: deterministic SG02 acceptance report/tests.
Acceptance:
1. minimum SG01 city fields are sufficient to create authenticated transport;
2. WB and Ozon adapters use the same context contract;
3. auth/connect/timeout/HTTP failures are explicit and not fake empty data;
4. credentials do not appear in ordinary logs, safe diagnostics or result-shaped objects;
5. transport creation/use requires no browser/profile/cookie preparation and no WB dest;
6. tests prove no silent direct-network bypass when proxy context is supplied.
Evidence: unit + cross-adapter + collector-boundary test suite with dummy secrets.
Failure: any SG02 acceptance clause lacks evidence; tests hide direct fallback; findings belonging to another SG are patched by widening this Task.
Prompt: `prompts/work/G01-SG02/PR03-ST02-T01-C01-I01.md`.

## 3. Dependency graph

`SG01 CityRecord -> PR01.ST01.T01 -> PR01.ST02.T01`

`PR01 -> PR02.ST01.T01 (requests)`
`PR01 -> PR02.ST02.T01 (curl_cffi)`

`PR02 adapters -> PR03.ST01.T01 -> PR03.ST02.T01`

No Task depends on live marketplace semantic success. SG02 can be contract-tested with deterministic fakes/mocks; live regional correctness is later SG evidence.

## 4. Write-scope hypothesis
Likely implementation scope, to be narrowed by exact Prompt/Worker evidence:
- new transport module(s) under `parser/core/`;
- narrow network-call integration in `parser/core/wb.py` and `parser/core/ozon.py`;
- tests/fixtures;
- no DB schema, result schema, scheduler, browser fallback, price/stock semantic changes.

## 5. Parent assembly
PR01 + PR02 + PR03 must compose exactly into SG02:
- PR01 proves authenticated safe proxy representation + typed failure boundary;
- PR02 proves both current HTTP stacks consume it;
- PR03 proves both collectors are actually bound to it and closes all SG02 AC.

SG02 then contributes to G01 A01/A04/A07/A10/A11/A12 but does not alone satisfy their marketplace/orchestration portions.
