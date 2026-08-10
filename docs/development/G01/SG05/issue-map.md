# SG05 durable identity map

Parent Subgoal: Issue #35

Materialized hierarchy:
- `G01.SG05.PR01` — Issue #79 — Legacy capability inventory and separation contract
  - `G01.SG05.PR01.ST01.T01` — Issue #82 — Inventory legacy regional entrypoints and artifacts
  - `G01.SG05.PR01.ST02.T01` — Issue #83 — Define primary-vs-fallback invocation boundary
- `G01.SG05.PR02` — Issue #80 — Explicit legacy fallback capabilities
  - `G01.SG05.PR02.ST01.T01` — Issue #84 — Preserve explicit Ozon legacy fallback path
  - `G01.SG05.PR02.ST02.T01` — Issue #85 — Preserve explicit legacy regional setup/support tools
- `G01.SG05.PR03` — Issue #81 — Separation regression and SG05 closure
  - `G01.SG05.PR03.ST01.T01` — Issue #86 — Prove primary legacy-independence and fallback reachability
  - `G01.SG05.PR03.ST02.T01` — Issue #87 — Prove SG05 acceptance and reverse assembly

Prompts are bound one-to-one under `prompts/work/G01-SG05/`.
Planning verdict: `SEMANTIC_COMPILE_PASS (vertical only; LEGACY_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`.
Implementation remains globally blocked pending SG06 and whole-G01 reverse compilation.
