# G01.SG02 virtual semantic compilation report

Verdict: **SEMANTIC_COMPILE_PASS (vertical only)**
Scope: SG02 proposed generation on planning branch. This is not implementation acceptance and does not authorize development before the whole G01 contour compiles.

## 1. Current-reality findings

### F1 — proxy value is already threaded but authentication contract is missing
Current `wb.py` and `ozon.py` accept a single optional `proxy` string and independently build `{http,https}` proxy mappings. The new accepted CityRecord instead carries `proxy`, `proxy_user`, `proxy_password` separately. Therefore the current implementation cannot consume the new minimum city contract without an explicit authenticated proxy-construction boundary.

### F2 — there is no shared transport authority
WB uses `requests`; Ozon uses `curl_cffi`; each module constructs proxy settings independently. This can drift and makes it impossible to prove once that city proxy authentication/redaction/failure rules apply to both.

### F3 — current WB transport failure can look like empty semantic data
WB returns `[]` on non-200 and after retry exhaustion/exceptions. That is insufficient for G01/SG02 because a network/proxy failure cannot be distinguished from a valid response producing no product rows.

### F4 — current Ozon failure classification collapses transport states
Ozon catches broad exceptions, prints them, and after strategies are exhausted returns `{"error":"403"}` regardless of whether the real cause was proxy/auth/connect/timeout/etc. This is not a reliable transport contract.

### F5 — raw exception logging is unsafe once credentials are embedded for library proxy auth
The current code prints exception text. A future authenticated proxy URI can appear inside library exception text, so SG02 must own redaction before proxy credentials are wired into the call paths.

### F6 — Ozon's current cookie requirement belongs to SG04, not SG02
Current `fetch_price` consumes cookies and current CLI loads them from a profile. SG02 can still compile if its curl_cffi adapter is cookie/profile-agnostic and treats caller-supplied cookies/session as opaque inputs. Removal/automatic bootstrap of that requirement remains SG04 authority.

### F7 — WB `dest` requirement belongs to SG03
Transport construction does not need `wb_dest`. Current collector semantics skip WB without dest, but changing that here would widen SG02 into SG03. SG02 must prove ProxyContext can be constructed and used without dest; SG03 later proves WB semantics without forced dest.

## 2. Virtual Prompt execution

### P1 — PR01.ST01.T01 ProxyContext
Expected implementation result:
- small `ProxyContext` value/factory in transport layer;
- authenticated endpoint formed from proxy address + separately supplied username/password;
- `host:port` accepted with one documented default scheme;
- explicit supported scheme preserved when included in `proxy`;
- credentials percent-encoded;
- safe representation excludes secret/raw authenticated URI;
- no `wb_dest`, profile or cookies dependency.

Result: **PASS**. No extra CityRecord field is structurally necessary. Exact live provider scheme is an integration fixture; it remains expressible inside the existing `proxy` value rather than a new column.

### P2 — PR01.ST02.T01 TransportOutcome
Expected result:
- one safe success/failure envelope;
- typed minimum categories: proxy/auth/connect, timeout, HTTP status, other transport, unexpected;
- no empty collection as transport failure;
- credential redaction.

Result: **PASS**. This closes F3/F4/F5 without adding marketplace semantics.

### P3 — PR02.ST01.T01 requests adapter
Expected result:
- adapter receives ProxyContext and request metadata;
- underlying `requests` invocation is inspectably proxied;
- exceptions/statuses map to common outcome;
- no direct fallback when context supplied.

Result: **PASS**. Current WB call shape can be passed through without price/stock changes.

### P4 — PR02.ST02.T01 curl_cffi adapter
Expected result:
- direct and Session curl_cffi calls both receive the same context;
- impersonation/cookies/session are caller inputs, not transport prerequisites;
- no unproxied homepage/bootstrap call;
- common safe outcome.

Result: **PASS**. Current Ozon call sequence can be transported without claiming SG04 completion.

### P5 — PR03.ST01.T01 collector binding
Expected result:
- WB and Ozon network call sites call adapters/shared context instead of independently constructing proxy mappings;
- primary CityRecord path builds ProxyContext before collectors;
- if context is supplied, no direct fallback;
- legacy/no-context operation may remain reachable for SG05 compatibility, but cannot masquerade as proxy-first primary operation;
- current WB price parser and Ozon cookie/price parser otherwise remain unchanged.

Result: **PASS WITH BOUNDARY CONDITION**.
Boundary condition: do not require current legacy `regions` objects to satisfy new CityRecord auth fields during this Task. SG01 CitySet is the primary input authority; legacy fallback reconciliation is SG05. Likewise do not remove Ozon cookies or change WB dest here.

### P6 — PR03.ST02.T01 closure evidence
Expected result:
- deterministic unit/cross-adapter/collector-boundary suite;
- accepted minimum city fields -> authenticated transport;
- both stacks bound;
- failures explicit;
- redaction proven;
- no browser/profile/cookies/dest prerequisite for transport construction/use;
- no silent direct bypass.

Result: **PASS**.

## 3. Child-to-parent composition

### PR01 -> SG02 contribution
Produces authenticated safe city proxy context + typed failure boundary.
Covers: proxy auth application basis, explicit failures, credential safety, minimum user contract.

### PR02 -> SG02 contribution
Proves both existing network libraries can consume the same context and failure contract.
Covers: WB/Ozon shared transport/context, no library-specific bypass.

### PR03 -> SG02 contribution
Proves the collectors' actual network boundaries are attached to the shared transport and supplies closure evidence.
Covers: proxy loaded-and-used invariant, no silent direct fallback, no manual-profile requirement inside transport.

Composition result: **PR01 + PR02 + PR03 fully assemble Issue #32 output/acceptance contract.**

## 4. Reverse assembly to G01

SG02 output composes with already-compiled SG01 output:

`SG01 CitySet -> SG02 ProxyContext/shared transport -> SG03/SG04 marketplace semantics -> SG06 complete run`.

G01 contribution check:
- A01 autonomous operation: SG02 supplies non-browser transport prerequisite; full proof waits SG04/SG06;
- A04 minimum proxy contract: SG02 proves no additional city field needed at transport layer;
- A05/A06 WB semantics: not owned, SG03 consumes SG02;
- A07 Ozon regional price: transport prerequisite only, SG04 owns semantic proof;
- A08 optional dest: SG02 is dest-independent; SG03 owns WB semantic proof;
- A09 fallback: SG05 remains separate and compatible via explicit legacy boundary;
- A10 failure isolation: SG02 supplies typed transport failures; SG06 supplies run-level accounting;
- A11 repeated operation: SG02 requires no manual transport preparation; SG04/SG06 finish proof;
- A12 complete matrix: SG06 consumes per-city SG02 context.

No G01 clause is contradicted or orphaned by this SG02 vertical.

## 5. Cross-SG interface findings retained for later compilation

### IF-SG03-01
WB collector currently requires `dest` and returns `[]` on transport failure. SG02 removes only the latter transport ambiguity. SG03 must change optional-dest semantics and stock extraction without reintroducing raw proxy handling.

### IF-SG04-01
Ozon currently requires cookies/profile upstream. SG04 must build whatever regional/session context is actually needed automatically **using the SG02 curl_cffi adapter/ProxyContext for every network call**.

### IF-SG05-01
Legacy fallback may have old region objects/raw proxy assumptions. SG05 must preserve fallback without making those objects primary CityRecord authority and without weakening the invariant that a supplied ProxyContext never silently falls back direct.

### IF-SG06-01
SG06 must construct/reuse the proper city ProxyContext from SG01 CitySet for each planned city unit and preserve typed SG02 failures into run outcomes.

## 6. Minimality / structural check
Six Tasks are minimum sufficient at this abstraction level:
- merging context and error model would mix secret construction with public failure semantics;
- merging the two adapters would hide materially different libraries;
- merging collector binding with closure tests would make acceptance evidence inseparable from implementation;
- no separate provider-management/API Task is needed for G01.

## 7. Final SG02 vertical verdict
**SEMANTIC_COMPILE_PASS**.

Development remains globally BLOCKED until SG03–SG06 also have complete vertical Prompts and the entire contour virtually compiles back into G01.
