# SG04 runtime evidence note

Ozon consumer regional/session behavior is treated as runtime evidence, not a stable assumed API contract.

The primary path may use automatically issued cookies/session state, but must not depend on manually warmed per-city profile files.

Two separate facts must be proven at point of use:
1. what a fresh proxy-bound Ozon session currently needs to retrieve the requested product page/price;
2. what observable signal is sufficient to accept the effective Ozon context as the requested city.

If #2 cannot be proven from the current minimum CityRecord, return `OZON_REGION_CONTEXT_UNPROVEN` and repair the canonical contract rather than accepting proxy geolocation as implicit proof.