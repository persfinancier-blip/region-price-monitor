# SG03 durable identity map

Parent Subgoal: Issue #33

Materialized hierarchy:
- `G01.SG03.PR01` — Issue #56 — WB endpoint evidence and stock semantics
  - `G01.SG03.PR01.ST01.T01` — Issue #60 — Capture current WB price/stock response evidence
  - `G01.SG03.PR01.ST02.T01` — Issue #61 — Define evidenced WB stock normalization contract
- `G01.SG03.PR02` — Issue #57 — Optional-dest WB request construction
  - `G01.SG03.PR02.ST01.T01` — Issue #62 — Build WB requests with optional dest through ProxyContext
- `G01.SG03.PR03` — Issue #58 — WB price and stock parser
  - `G01.SG03.PR03.ST01.T01` — Issue #63 — Parse evidenced WB price and stock fields
  - `G01.SG03.PR03.ST02.T01` — Issue #64 — Classify zero stock, missing product and transport failures
- `G01.SG03.PR04` — Issue #59 — WB collector integration and SG03 closure
  - `G01.SG03.PR04.ST01.T01` — Issue #65 — Integrate WB collector for optional-dest product-city outcomes
  - `G01.SG03.PR04.ST02.T01` — Issue #66 — Prove WB regional price-stock contract and reverse assembly

Initial Prompts are one-to-one under `prompts/work/G01-SG03/`.

Planning status: `SEMANTIC_COMPILE_PASS (vertical only; RUNTIME_PROBE_REQUIRED)`.

Execution-readiness distinction:
- all Tasks/Prompts may exist in advance;
- #60 is the point-of-use current-endpoint evidence prerequisite;
- #61/#63/#64/#65/#66 cannot honestly close the stock path if #60 emits `WB_STOCK_CONTRACT_UNPROVEN`.

Implementation remains globally blocked pending SG04-SG06 and full G01 reverse semantic compilation.
