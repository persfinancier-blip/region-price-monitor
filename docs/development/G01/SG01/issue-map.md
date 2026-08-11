# SG01 durable identity map

Parent Subgoal: #31

Materialized hierarchy:
- `G01.SG01.PR01` Product source preservation and normalization — #38
  - `G01.SG01.PR01.ST01.T01` Normalize and preserve product sources — #41
- `G01.SG01.PR02` City source acquisition and normalization — #39
  - `G01.SG01.PR02.ST01.T01` Define minimum CityRecord normalization — #42
  - `G01.SG01.PR02.ST02.T01` Load cities from file — #43
  - `G01.SG01.PR02.ST03.T01` Load cities from PostgreSQL — #44
- `G01.SG01.PR03` Source-neutral input handoff and SG01 closure — #40
  - `G01.SG01.PR03.ST01.T01` Compose normalized product and city inputs — #45
  - `G01.SG01.PR03.ST02.T01` Prove SG01 source parity and minimum contract — #46

Prompt identities:
- #41 -> `prompts/work/G01-SG01/PR01-ST01-T01-C01-I01.md`
- #42 -> `prompts/work/G01-SG01/PR02-ST01-T01-C01-I01.md`
- #43 -> `prompts/work/G01-SG01/PR02-ST02-T01-C01-I01.md`
- #44 -> `prompts/work/G01-SG01/PR02-ST03-T01-C01-I01.md`
- #45 -> `prompts/work/G01-SG01/PR03-ST01-T01-C01-I01.md`
- #46 -> `prompts/work/G01-SG01/PR03-ST02-T01-C01-I01.md`

Semantic contracts: `vertical.md`. Virtual execution verdict: `compile-report.md`.

Current status: SG01 vertical `SEMANTIC_COMPILE_PASS`; implementation still blocked by incomplete whole-G01 compilation.
