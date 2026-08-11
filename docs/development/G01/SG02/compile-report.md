# G01.SG02 Semantic Compilation Report — repaired C02 boundary

Parent: Issue #32
Planning branch: `brain/g01-regional-monitor-plan`
Repair note: `docs/development/G01/SG02/C02-repair.md`

## Verdict

`SEMANTIC_COMPILE_PASS (vertical only; repaired C02 boundary)`

The original SG02 structure remains valid: one canonical authenticated/redacted `ProxyContext`, typed transport outcomes, `requests` adapter, `curl_cffi` adapter, and collector handoff/closure. Whole-G01 reverse compilation found one stale interface constraint in C01 Tasks #54/#55: they treated all Ozon primary network traffic as if it must transit through `curl_cffi`. Active SG04 C02 legitimately allows a hidden/headless Selenium/Chrome engine.

The repair changes **library routing**, not proxy authority.

## Canonical proxy-authority model

`CityRecord -> SG02 ProxyContext`

From that one authority:
- current WB HTTP -> SG02 `requests` adapter;
- current Ozon HTTP -> SG02 `curl_cffi` adapter;
- SG04 hidden-browser path -> SG04-owned browser proxy adaptation derived from the same ProxyContext.

A browser adapter is not required to tunnel through `curl_cffi`. It is forbidden to independently invent/read a second raw proxy host/user/password authority or silently go direct.

## Active Prompt generations

Unchanged C01 Tasks:
- #50 ProxyContext construction;
- #51 typed/redacted transport outcome;
- #52 requests adapter;
- #53 curl_cffi adapter.

Repaired active C02 Tasks:
- #54 `PR03-ST01-T01-C02.I01.md` — collector/engine proxy-authority handoff;
- #55 `PR03-ST02-T01-C02.I01.md` — repaired SG02 closure.

Their C01 Prompts remain immutable superseded history.

## Virtual execution after repair

### PR01 — ProxyContext + safe outcomes
PASS.
Minimum SG01 city fields remain sufficient; `wb_dest`, browser profile and cookies are irrelevant to transport construction. Credentials remain redacted and transport failures remain explicit.

### PR02 — current HTTP adapters
PASS.
`requests` and `curl_cffi` consume the same ProxyContext. These adapters remain useful/required for current WB/Ozon HTTP paths; allowing a later browser engine does not invalidate them.

### PR03.ST01 C02 — engine handoff
PASS.
Current HTTP calls bind to SG02 adapters. SG04 may project/adapt the same ProxyContext into Selenium/Chrome settings under SG04 ownership. No second proxy authority and no direct fallback are allowed.

### PR03.ST02 C02 — closure
PASS.
The acceptance invariant is now correctly stated as **one ProxyContext authority across primary network engines**, not one HTTP library across all engines.

## Reverse assembly

- PR01 provides authenticated safe city proxy authority and typed HTTP transport failures.
- PR02 provides current library adapters.
- PR03 provides the durable cross-marketplace/cross-engine handoff rule and closure evidence.

Their composition still fully satisfies Issue #32.

## Cross-SG compatibility

### SG01 -> SG02
PASS. CityRecord remains exactly `city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`.

### SG02 -> SG03
PASS. WB consumes ProxyContext via requests adapter; SG03 owns dest/stock/price semantics.

### SG02 -> SG04 C02
PASS after repair. Ozon `curl_cffi` paths consume SG02 adapter; hidden Selenium/Chrome may consume an SG04-specific browser adaptation derived from the same ProxyContext. SG04 owns browser/session/location/city-verification lifecycle.

### SG02 -> SG05
PASS. Legacy authenticated profile/cookie fallback remains separate and cannot weaken supplied-ProxyContext no-direct-fallback behavior in primary.

### SG02 -> SG06
PASS. SG06 uses CityRecord -> ProxyContext as city network authority and persists typed failures instead of empty business data.

## Fail conditions retained
- proxy fields loaded but ignored;
- any primary engine silently goes direct when ProxyContext exists;
- browser engine independently reconstructs proxy credentials from another source;
- credentials appear in logs/results/evidence;
- transport failure becomes valid empty/zero marketplace data;
- SG02 absorbs SG04 browser/context semantics.

## Final repaired SG02 verdict

`SEMANTIC_COMPILE_PASS`.

The whole-G01 compiler must use active #54/#55 C02 Prompts and ignore their superseded C01 library-only constraint.