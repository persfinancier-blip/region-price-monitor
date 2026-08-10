# SG04 durable identity map

Parent Subgoal: Issue #34

Proposed hierarchy:
- `G01.SG04.PR01` Current Ozon regional/session evidence and context contract
  - `G01.SG04.PR01.ST01.T01` Capture fresh-session proxy-first Ozon behavior
  - `G01.SG04.PR01.ST02.T01` Define evidenced Ozon regional bootstrap and verification contract
- `G01.SG04.PR02` Automatic proxy-bound Ozon session/context bootstrap
  - `G01.SG04.PR02.ST01.T01` Bootstrap fresh Ozon session through ProxyContext
  - `G01.SG04.PR02.ST02.T01` Verify city context and support autonomous refresh/retry
- `G01.SG04.PR03` Ozon regional price parsing and semantic outcomes
  - `G01.SG04.PR03.ST01.T01` Validate and preserve requested-product webPrice parsing
  - `G01.SG04.PR03.ST02.T01` Classify Ozon transport, context and semantic failures
- `G01.SG04.PR04` Ozon collector integration and SG04 closure
  - `G01.SG04.PR04.ST01.T01` Integrate proxy-first Ozon product-city observations
  - `G01.SG04.PR04.ST02.T01` Prove no-manual-warm repeated-run contract and reverse assembly

Exact GitHub Issue IDs are filled after materialization.
Prompts are one-to-one under `prompts/work/G01-SG04/`.