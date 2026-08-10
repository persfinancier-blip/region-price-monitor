# G01.SG04 process contracts

Parent: Issue #34
Canonical vertical: `docs/development/G01/SG04/vertical.md`

## G01.SG04.PR01 — Current Ozon regional/session evidence and context contract
Input: representative Ozon SKUs, CityRecord proxy data, SG02 transport.
Output: sanitized fresh-session evidence + evidence-backed regional/bootstrap verification contract, or explicit unproven verdict.
Acceptance: no guessed city/session semantics; no manual profile dependency normalized into primary path; no new mandatory CityRecord field without canonical repair.
Evidence: probe logs/fixtures/schema/state map with secrets removed.
Failure: context behavior is assumed from IP or legacy cookies rather than observed.

## G01.SG04.PR02 — Automatic proxy-bound Ozon session/context bootstrap
Input: accepted PR01 contract + CityRecord + SG02 curl_cffi transport.
Output: automatically created and verified `OzonContext` for requested city with bounded autonomous refresh/rebootstrap.
Acceptance: no manual cookies/profile/browser; every request through ProxyContext; context mismatch/unproven explicit; secret-safe; bounded retries.
Evidence: session-call inspection, context-verification tests, refresh/repeat tests.
Failure: direct fallback, human prerequisite, wrong/unverified city accepted.

## G01.SG04.PR03 — Ozon regional price parsing and semantic outcomes
Input: verified OzonContext product responses + SG02 TransportOutcome.
Output: requested-SKU `webPrice` price fields or typed transport/context/session/semantic failure.
Acceptance: no arbitrary ₽ scraping; no broad error collapse to 403; city/SKU retained on failure.
Evidence: fixtures + parser/classifier tests.
Failure: unknown city or failure presented as valid price.

## G01.SG04.PR04 — Ozon collector integration and SG04 closure
Input: ProductSet Ozon subset + CitySet + accepted PR02/PR03.
Output: one typed Ozon outcome per requested SKU × city + repeat-run/no-manual-warm acceptance evidence.
Acceptance: primary collector has no `cookies.json`/profile prerequisite; first and repeated run require no human browser; siblings survive individual failure.
Evidence: collector spies/integration fixtures + reverse-assembly report.
Failure: manual warm remains part of normal path or SG05/SG06 responsibilities are absorbed.