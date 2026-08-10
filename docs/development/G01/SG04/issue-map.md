# SG04 durable identity map

Parent Subgoal: Issue #34

Materialized hierarchy:
- `G01.SG04.PR01` — Issue #67 — Current Ozon regional/session evidence and context contract
  - `G01.SG04.PR01.ST01.T01` — Issue #71 — Capture fresh-session proxy-first Ozon behavior
  - `G01.SG04.PR01.ST02.T01` — Issue #72 — Define evidenced Ozon regional bootstrap and verification contract
- `G01.SG04.PR02` — Issue #68 — Automatic proxy-bound Ozon session/context bootstrap
  - `G01.SG04.PR02.ST01.T01` — Issue #73 — Bootstrap fresh Ozon session through ProxyContext
  - `G01.SG04.PR02.ST02.T01` — Issue #74 — Verify city context and support autonomous refresh
- `G01.SG04.PR03` — Issue #69 — Ozon regional price parsing and semantic outcomes
  - `G01.SG04.PR03.ST01.T01` — Issue #75 — Validate and preserve requested-product webPrice parsing
  - `G01.SG04.PR03.ST02.T01` — Issue #76 — Classify Ozon transport, context and semantic failures
- `G01.SG04.PR04` — Issue #70 — Ozon collector integration and SG04 closure
  - `G01.SG04.PR04.ST01.T01` — Issue #77 — Integrate proxy-first Ozon product-city observations
  - `G01.SG04.PR04.ST02.T01` — Issue #78 — Prove no-manual-warm Ozon repeat-run contract and reverse assembly

Prompts are bound one-to-one under `prompts/work/G01-SG04/`.
Planning verdict: `SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_CONTEXT_PROBE_REQUIRED)`; implementation remains globally blocked pending full G01 compilation.