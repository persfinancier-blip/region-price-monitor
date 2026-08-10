# G01.SG05 Processes

Canonical vertical: `docs/development/G01/SG05/vertical.md`
Parent Subgoal: Issue #35

## G01.SG05.PR01 — Legacy capability inventory and separation contract

### Input
Current legacy browser/profile/cookies/WB-dest tooling + SG01–SG04 primary contracts.

### Output
Complete legacy entrypoint/artifact inventory and deterministic primary-vs-fallback invocation boundary.

### Stages
- ST01 Inventory legacy regional entrypoints and artifacts
- ST02 Define primary-vs-fallback invocation boundary

### Acceptance
Primary never needs profile/cookies/manual dest preparation; explicit operator intent gates interactive fallback; all useful legacy entrypoints are preserved in scope.

## G01.SG05.PR02 — Explicit legacy fallback capabilities

### Input
Accepted PR01 inventory/boundary + existing implementations.

### Output
Explicitly invokable Ozon legacy fallback and legacy regional setup/support tools, isolated from primary runtime.

### Stages
- ST01 Preserve explicit Ozon legacy fallback path
- ST02 Preserve explicit legacy regional setup/support tools

### Acceptance
Existing profiles/cookies/browser fallback and manual WB dest capture remain usable; none is automatically invoked by primary collection.

## G01.SG05.PR03 — Separation regression and SG05 closure

### Input
Accepted PR01/PR02 outputs + SG01–SG04 primary interfaces.

### Output
Primary-isolation tests, fallback regression/smoke evidence, and SG05 reverse-assembly proof.

### Stages
- ST01 Prove primary legacy-independence and fallback reachability
- ST02 Prove SG05 acceptance and reverse assembly

### Acceptance
Both sides are independently usable: primary without legacy assets/actions, legacy via explicit invocation. Findings outside this boundary route to SG03/SG04/SG06 rather than widening SG05.
