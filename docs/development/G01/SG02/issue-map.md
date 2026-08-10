# SG02 durable identity map

Parent Subgoal: Issue #32

Materialized hierarchy:
- `G01.SG02.PR01` — Issue #47 — Authenticated proxy context and safe transport contract
  - `G01.SG02.PR01.ST01.T01` — Issue #50 — Build authenticated ProxyContext from minimum CityRecord
  - `G01.SG02.PR01.ST02.T01` — Issue #51 — Define typed transport outcomes and safe errors
- `G01.SG02.PR02` — Issue #48 — HTTP-stack proxy adapters
  - `G01.SG02.PR02.ST01.T01` — Issue #52 — Route requests traffic through ProxyContext
  - `G01.SG02.PR02.ST02.T01` — Issue #53 — Route curl_cffi traffic through ProxyContext
- `G01.SG02.PR03` — Issue #49 — Marketplace transport handoff and SG02 closure
  - `G01.SG02.PR03.ST01.T01` — Issue #54 — Bind WB and Ozon request paths to shared transport
  - `G01.SG02.PR03.ST02.T01` — Issue #55 — Prove proxy-first transport contract

Prompts are bound one-to-one under `prompts/work/G01-SG02/`.
Planning status: `SEMANTIC_COMPILE_PASS (vertical only)`; implementation remains globally blocked pending full G01 compilation.
