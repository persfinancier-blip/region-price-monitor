# SG04 runtime evidence note — C02

Ozon consumer regional/session behavior is runtime evidence, not a stable assumed API contract.

Primary may use automatically issued **non-personalized technical cookies/session state** and may use **hidden/headless Selenium/Chrome** when evidence shows a real browser is needed. What SG04 primary does **not** require is the personalized authenticated user cookies/tokens used by the current legacy fallback; those belong to SG05.

What primary may not require is human browser work or a manually maintained per-city profile.

Three facts must be proven at point of use:
1. which autonomous engine strategy currently works for the new proxy-first Ozon path: `curl_cffi`, hidden Selenium/Chrome, or a bounded combination;
2. if hidden browser is used, that its network traffic/proxy routing is derived from the same requested-city SG02 ProxyContext and never silently goes direct;
3. what observable signal is sufficient to accept effective Ozon context as the requested city.

Engine order must be evidence-driven. The contract does not assume `curl_cffi` must run before browser, nor that browser must always run.

Important separation:
```text
SG04 new proxy-first:
  no legacy personalized Ozon login cookies/tokens prerequisite

SG05 current working fallback:
  personalized authenticated user cookies/tokens are required runtime secret material
```

If #2 cannot be proven, return `OZON_BROWSER_PROXY_BINDING_UNPROVEN`.
If #3 cannot be proven from the minimum CityRecord, return `OZON_REGION_CONTEXT_UNPROVEN` and repair the canonical contract rather than accepting proxy geolocation as implicit proof.

A captcha/challenge that requires a human is **not** autonomous success. Primary returns an explicit failure; SG05 visible/manual authenticated fallback remains separately and intentionally invokable.
