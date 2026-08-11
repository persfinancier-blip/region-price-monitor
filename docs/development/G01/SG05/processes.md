# G01.SG05 Processes — active cycle C02

Canonical vertical: `docs/development/G01/SG05/vertical.md`
Parent Subgoal: Issue #35

## G01.SG05.PR01 — Legacy capability inventory and separation contract

### Input
Current legacy browser/profile/cookies/WB-dest tooling + SG01–SG04 primary contracts.

### Output
Complete legacy entrypoint/artifact inventory and deterministic primary-vs-fallback invocation boundary, explicitly recording that current working Ozon fallback cookies are **personalized authenticated user cookies/tokens** and secret runtime material.

### Stages
- ST01 Inventory legacy regional entrypoints, authenticated-cookie semantics and artifacts
- ST02 Define primary-vs-fallback invocation/credential boundary

### Acceptance
New proxy-first primary never needs the legacy authenticated profile/cookies; explicit operator intent gates legacy; current fallback retains personalized authenticated-cookie semantics; raw secrets never enter Git/log/results/evidence.

## G01.SG05.PR02 — Explicit authenticated legacy fallback capabilities

### Input
Accepted PR01 inventory/boundary + existing implementations + runtime-local authenticated profile/cookies.

### Output
Explicitly invokable Ozon authenticated legacy fallback and legacy regional setup/support tools, isolated from primary runtime.

### Stages
- ST01 Preserve explicit Ozon authenticated legacy fallback path
- ST02 Preserve explicit legacy authenticated-profile regional setup/support tools

### Acceptance
Existing authenticated profiles/cookies/browser fallback and manual WB dest capture remain usable; anonymous/generic substitute cookies do not count as compatibility; none is automatically invoked by primary collection.

## G01.SG05.PR03 — Separation regression and SG05 closure

### Input
Accepted PR01/PR02 outputs + SG01–SG04 primary interfaces.

### Output
Primary-isolation tests, authenticated-fallback regression/smoke evidence, and SG05 reverse-assembly proof.

### Stages
- ST01 Prove primary legacy-independence and authenticated fallback reachability
- ST02 Prove SG05 C02 acceptance and reverse assembly

### Acceptance
Both sides are independently correct: new proxy-first primary without legacy authenticated assets/actions; current legacy path via explicit invocation with personalized authenticated user cookies/profile. Findings outside this boundary route to SG03/SG04/SG06 rather than widening SG05.
