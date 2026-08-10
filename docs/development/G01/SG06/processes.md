# G01.SG06 Process Contracts

Parent: Issue #36
Canonical vertical: `docs/development/G01/SG06/vertical.md`

## PR01 — RunPlan expansion and exact outcome accounting
Input: SG01 ProductSet + CitySet + enabled marketplaces; SG03/SG04 typed outcomes.
Output: immutable run plan with expected semantic keys + reconciled one-terminal-outcome-per-key result set.
Acceptance: plan exists before network execution; missing/duplicate/unexpected outcomes explicit; terminal count equals planned count; no marketplace semantic reinterpretation.
Failure: error/empty collector response shrinks matrix silently.

## PR02 — Canonical RunResult and lossless persistence
Input: reconciled SG03/SG04 outcomes.
Output: canonical RunResult rows + complete file and PostgreSQL persistence.
Acceptance: identity/status/error/price persist; WB stock/availability persist; failures are rows, not log-only events; no invented defaults; one run_id across targets.
Failure: persistence loses city/status/error/stock or filters failures.

## PR03 — Autonomous primary runner and repeated-run lifecycle
Input: RunPlan, CitySet, SG02 ProxyContext, SG03/SG04 collectors, configured sources/outputs.
Output: primary execution engine + non-interactive entrypoint + repeat-run/resource-lifecycle evidence.
Acceptance: per-city proxy authority preserved; failures isolated; no SG05 implicit fallback; no `input()`/legacy preparation in scheduler-ready primary; distinct run identity and bounded resources across repeated runs.
Failure: current legacy config/profile workflow remains prerequisite or one unit failure aborts unaccounted siblings.

## PR04 — End-to-end SG06 acceptance and reverse assembly
Input: accepted PR01–PR03 outputs and deterministic mixed-outcome fixture.
Output: matrix/persistence parity proof + SG06 acceptance/reverse assembly.
Acceptance: exact expected count, all terminal rows, file/PG semantic parity, all Issue #36 clauses covered, no cross-SG weakening.
Failure: orphan acceptance clause, silent cardinality drift, semantic loss, or structural interface mismatch.