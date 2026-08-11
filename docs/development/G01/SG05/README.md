# G01.SG05 — Legacy Regional Fallback Preservation

Parent Subgoal: Issue #35

Canonical planning files:
- `vertical.md`
- `processes.md`
- `compile-report.md`
- `issue-map.md`

Initial Prompts: `prompts/work/G01-SG05/`

Planning verdict: `SEMANTIC_COMPILE_PASS (vertical only; LEGACY_DESKTOP_SMOKE_REQUIRED_AT_EXECUTION)`.

Core invariant: legacy browser/profile/cookies functionality remains intentionally reachable as reserve capability, but primary proxy-first startup/collection has zero implicit dependency on it. Automatic browser fallback is not part of primary G01 behavior.
