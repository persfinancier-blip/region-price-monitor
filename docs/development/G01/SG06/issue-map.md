# SG06 durable identity map

Parent Subgoal: Issue #36

Materialized hierarchy:
- `G01.SG06.PR01` — Issue #88 — RunPlan expansion and exact outcome accounting
  - `G01.SG06.PR01.ST01.T01` — Issue #92 — Build deterministic RunPlan
  - `G01.SG06.PR01.ST02.T01` — Issue #93 — Reconcile collector outcomes to RunPlan
- `G01.SG06.PR02` — Issue #89 — Canonical RunResult and lossless persistence
  - `G01.SG06.PR02.ST01.T01` — Issue #94 — Normalize typed outcomes into canonical RunResult
  - `G01.SG06.PR02.ST02.T01` — Issue #95 — Persist complete RunResultSet to file
  - `G01.SG06.PR02.ST03.T01` — Issue #96 — Migrate and persist complete RunResultSet to PostgreSQL
- `G01.SG06.PR03` — Issue #90 — Autonomous primary runner and repeated-run lifecycle
  - `G01.SG06.PR03.ST01.T01` — Issue #97 — Compose collectors with per-unit failure isolation
  - `G01.SG06.PR03.ST02.T01` — Issue #98 — Provide non-interactive scheduler-ready primary invocation
  - `G01.SG06.PR03.ST03.T01` — Issue #99 — Prove repeated-run lifecycle and resource isolation
  - `G01.SG06.PR03.ST04.T01` — Issue #102 — Add double-click local Git bootstrap/sync launcher
- `G01.SG06.PR04` — Issue #91 — End-to-end SG06 acceptance and reverse assembly
  - `G01.SG06.PR04.ST01.T01` — Issue #100 — Prove complete mixed-outcome matrix and persistence parity
  - `G01.SG06.PR04.ST02.T01` — Issue #101 — Prove SG06 acceptance and reverse assembly

Prompts are bound one-to-one under `prompts/work/G01-SG06/`.
Task #102 Prompt: `prompts/work/G01-SG06/PR03-ST04-T01-C01-I01.md`.

SG06 planning verdict: `SEMANTIC_COMPILE_PASS (vertical only)` plus `SEMANTIC_COMPILE_PASS (SG06 local-delivery extension)`.

Base whole-G01 report: `docs/development/G01/full-compile-report.md`.
Normative active-generation addendum: `docs/development/G01/full-compile-addendum-local-delivery.md`.
Current global verdict: **`SEMANTIC_COMPILE_PASS (WHOLE G01 ACTIVE 44-PROMPT GENERATION)`**.

Implementation execution is permitted in dependency/serialization order; #102 executes after #98 and must serialize with launcher/installer file changes. Runtime gates remain authoritative.