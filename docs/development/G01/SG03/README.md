# G01.SG03 planning index

Parent Subgoal: Issue #33 — Wildberries Regional Price and Stock.

Canonical proposed artifacts:
- `vertical.md` — complete Process→Stage→Task contracts and dependencies;
- `processes.md` — Process-level contracts;
- `compile-report.md` — virtual execution and reverse composition;
- `issue-map.md` — durable GitHub identity map after materialization;
- `prompts/work/G01-SG03/` — seven initial immutable Prompt candidates.

Planning verdict: `SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_PROBE_REQUIRED)`.

Critical rule: current `card.wb.ru/cards/v4/detail` stock schema is not guessed. `PR01.ST01.T01` must capture current sanitized endpoint evidence before stock parser semantics become execution-ready. If evidence is insufficient, emit `WB_STOCK_CONTRACT_UNPROVEN` and repair the model rather than inferring stock from price.

Implementation remains blocked until SG04–SG06 and the complete G01 reverse semantic compilation pass.
