# SG05 durable identity map — active cycle C02

Parent Subgoal: Issue #35

Materialized hierarchy:
- `G01.SG05.PR01` — Issue #79 — Legacy capability inventory and separation contract
  - `G01.SG05.PR01.ST01.T01` — Issue #82 — Inventory legacy regional entrypoints and authenticated-cookie artifacts
    - active prompt: `prompts/work/G01-SG05/PR01-ST01-T01-C02.I01.md`
  - `G01.SG05.PR01.ST02.T01` — Issue #83 — Define primary-vs-fallback invocation/credential boundary
    - active prompt: `prompts/work/G01-SG05/PR01-ST02-T01-C02.I01.md`
- `G01.SG05.PR02` — Issue #80 — Explicit legacy fallback capabilities
  - `G01.SG05.PR02.ST01.T01` — Issue #84 — Preserve explicit authenticated Ozon legacy fallback path
    - active prompt: `prompts/work/G01-SG05/PR02-ST01-T01-C02.I01.md`
  - `G01.SG05.PR02.ST02.T01` — Issue #85 — Preserve explicit authenticated legacy regional setup/support tools
    - active prompt: `prompts/work/G01-SG05/PR02-ST02-T01-C02.I01.md`
- `G01.SG05.PR03` — Issue #81 — Separation regression and SG05 closure
  - `G01.SG05.PR03.ST01.T01` — Issue #86 — Prove primary legacy-independence and authenticated fallback reachability
    - active prompt: `prompts/work/G01-SG05/PR03-ST01-T01-C02.I01.md`
  - `G01.SG05.PR03.ST02.T01` — Issue #87 — Prove SG05 C02 acceptance and reverse assembly
    - active prompt: `prompts/work/G01-SG05/PR03-ST02-T01-C02.I01.md`

C01 Prompt files remain immutable superseded history.

Critical C02 invariant: current working fallback requires personalized authenticated Ozon cookies/tokens; these secrets remain runtime-local and are not required by the new SG04 proxy-first mechanism.

Planning verdict: `SEMANTIC_COMPILE_PASS (vertical only; LEGACY_AUTHENTICATED_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`.
Implementation remains globally blocked pending SG06 and whole-G01 reverse compilation.
