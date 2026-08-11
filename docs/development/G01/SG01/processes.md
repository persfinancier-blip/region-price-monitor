# SG01 Process contracts

Parent: #31

## G01.SG01.PR01 — Product source preservation and normalization
Stages:
- ST01 Product normalized-source boundary

Output: canonical ProductSet from existing file/DB paths.

## G01.SG01.PR02 — City source acquisition and normalization
Stages:
- ST01 Canonical CityRecord and validation
- ST02 City file source
- ST03 City PostgreSQL source

Output: canonical CitySet from file or DB under the minimum five-field contract.

## G01.SG01.PR03 — Source-neutral input handoff and SG01 closure
Stages:
- ST01 Unified input composition
- ST02 Contract parity and minimality gate

Output: source-neutral ProductSet + CitySet handoff plus SG01 acceptance evidence.

Full contracts and dependencies: `vertical.md`.
