# G01.SG04 process contracts — active C02

Parent: Issue #34
Canonical vertical: `docs/development/G01/SG04/vertical.md`
Active Prompt cycle: `C02.I01`; C01 retained as superseded history.

## G01.SG04.PR01 — Current Ozon regional/session evidence and autonomous-engine contract
Input: representative Ozon SKUs, CityRecord proxy data, SG02 ProxyContext.
Output: sanitized evidence for lightweight HTTP and, where needed, hidden/headless Selenium/Chrome + evidence-backed engine/bootstrap/city-verification contract, or explicit unproven verdict.
Acceptance: no guessed city/session semantics; hidden browser allowed only with zero human action; no manual profile dependency normalized into primary; no proxy-IP-as-city assumption; browser proxy binding must be proven; no new mandatory CityRecord field without canonical repair.
Evidence: probe logs/fixtures/state map with secrets removed.
Failure: engine/context behavior assumed, browser goes direct, or manual flow is disguised as automatic.

## G01.SG04.PR02 — Automatic proxy-bound Ozon context engine
Input: accepted PR01 C02 contract + CityRecord + SG02 ProxyContext/HTTP interfaces.
Output: automatically created, engine-provenance-aware and verified `OzonContext` for requested city with bounded autonomous refresh/rebootstrap.
Acceptance: no manually maintained cookies/profile; `curl_cffi` and/or hidden Selenium/Chrome only as evidenced; every engine derives proxy config from ProxyContext; no human interaction; wrong/unverified city explicit; browser lifecycle bounded/cleaned; no direct fallback.
Evidence: HTTP/browser call inspection, proxy-binding tests, context-verification fixtures, refresh/repeat tests.
Failure: direct browser traffic, human prerequisite, orphan browser processes, wrong/unverified city accepted.

## G01.SG04.PR03 — Ozon regional price parsing and semantic outcomes
Input: verified C02 OzonContext content/state + SG02/hidden-browser engine outcomes.
Output: requested-SKU `webPrice` price fields or typed transport/browser/context/session/semantic failure.
Acceptance: parser engine-neutral; no arbitrary ₽ scraping; browser-specific failures distinct; no broad collapse to synthetic 403; city/SKU retained.
Evidence: equivalent-content fixtures + parser/classifier tests.
Failure: engine choice changes semantic price meaning or failure is presented as valid price.

## G01.SG04.PR04 — Ozon collector integration and SG04 closure
Input: Ozon ProductSet subset + CitySet + accepted PR02/PR03 C02 interfaces.
Output: one typed Ozon outcome per requested SKU × city + no-human-work repeat-run acceptance evidence.
Acceptance: primary collector has no manually prepared profile/cookie prerequisite; hidden/headless browser may run automatically; no implicit visible/manual fallback; every engine uses CityRecord ProxyContext; siblings survive individual failure.
Evidence: collector spies/integration fixtures + hidden-browser lifecycle/proxy evidence + reverse-assembly report.
Failure: human warm remains normal path, browser bypasses proxy, or SG05/SG06 responsibilities are absorbed.