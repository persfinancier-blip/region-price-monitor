# G01.SG05 — Legacy Regional Fallback Preservation — vertical decomposition

Parent Goal: G01 / Issue #30
Parent Subgoal: Issue #35
Planning branch: `brain/g01-regional-monitor-plan`
Status: PROPOSED / implementation globally blocked until full G01 semantic compilation PASS.

## SG05 contract restatement

Preserve the existing interactive browser/profile/cookies regional workflow as a usable reserve capability, while making it impossible for primary proxy-first operation to depend on legacy preparation implicitly.

Primary invariant:

```text
primary proxy-first run
  != review_profiles
  != repair_regions
  != add_new_regions
  != warm_region
  != browser_fetch_prices
  != get_wb_dest prerequisite
```

Legacy invariant:

```text
operator explicitly chooses legacy/fallback capability
  -> existing browser/profile/cookies tooling remains reachable
  -> result/failure is explicit
```

Automatic fallback switching is NOT required by G01. A primary failure must not silently launch a browser.

---

## PR01 — Legacy capability inventory and separation contract

### Purpose
Freeze what must remain available and define the exact primary/legacy boundary before changing call paths.

### Input contract
- current `parser/core/cli.py`;
- current `parser/core/warm_browser.py`;
- current `parser/core/ozon.py` legacy cookie loader/fetch path;
- SG01 CityRecord and SG02–SG04 primary interfaces.

### Output contract
- evidence-backed inventory of legacy entrypoints/artifacts;
- explicit fallback invocation contract;
- primary-path isolation contract proving legacy profile/cookie/dest preparation is not a prerequisite.

### ST01 / T01 — Inventory legacy regional entrypoints and artifacts
Output: exact map for `review_profiles`, `repair_regions`, `add_new_regions`, `warm_region`, `browser_fetch_prices`, `get_wb_dest`, `load_cookies`, profile directories/cookies files and legacy config keys.

### ST02 / T01 — Define primary-vs-fallback invocation boundary
Output: deterministic rule that primary never implicitly invokes interactive legacy operations, while explicit fallback/operator mode may invoke them.

### Acceptance
- no useful legacy capability omitted from inventory;
- no legacy artifact added to minimum CityRecord;
- automatic browser launch after primary Ozon failure is classified as legacy behavior to remove from primary path;
- explicit operator intent is required to enter interactive fallback;
- SG05 does not design automatic fallback policy.

### Failure
- legacy preparation remains hidden in primary startup;
- `ozon_profile_dir`/`cookies.json` becomes required primary input;
- SG05 deletes legacy behavior before an explicit replacement boundary exists.

---

## PR02 — Explicit legacy fallback capabilities

### Purpose
Preserve the existing reserve mechanisms behind intentional entrypoints without contaminating primary runtime contracts.

### Input contract
Accepted PR01 inventory/boundary + current legacy implementations.

### Output contract
- explicit Ozon legacy profile/cookies/browser fallback capability;
- explicit legacy regional setup/support capability including manual Ozon warm/profile repair and optional WB dest capture;
- neither is automatically invoked by primary proxy-first collection.

### ST01 / T01 — Preserve explicit Ozon legacy fallback path
Output: intentionally invokable Ozon fallback that can consume existing profile/cookies and use `browser_fetch_prices` where needed, with explicit fallback provenance/status.

### ST02 / T01 — Preserve explicit legacy regional setup/support tools
Output: intentionally invokable legacy maintenance path for `review_profiles`/`repair_regions`/`add_new_regions`, `warm_region`, and `get_wb_dest`, isolated from normal primary startup.

### Acceptance
- existing profiles/cookies remain usable as reserve input;
- browser fallback remains reachable only by explicit legacy/fallback invocation;
- manual WB dest capture remains available as optional operator tool, not a prerequisite for no-dest primary WB;
- primary CityRecord stays `{city, proxy, proxy_user, proxy_password, wb_dest?}`;
- no persistence/scheduler redesign.

### Failure
- fallback exists only as dead/unreachable code;
- primary failure silently launches browser;
- explicit fallback mutates the meaning of primary CityRecord;
- SG05 absorbs SG06 orchestration policy.

---

## PR03 — Separation regression and SG05 closure

### Purpose
Prove both sides at once: legacy still works as a reserve capability and primary operation has zero legacy preparation dependency.

### Input contract
Accepted PR01/PR02 outputs + SG01–SG04 primary interfaces.

### Output contract
- deterministic primary-isolation regression evidence;
- legacy fallback smoke/regression evidence;
- reverse assembly proof into SG05 and G01.

### ST01 / T01 — Prove primary path is legacy-independent and fallback remains reachable
Output: tests/spies showing no primary calls to interactive legacy entrypoints, plus deterministic explicit fallback invocation tests and desktop/live smoke plan where browser execution is environment-dependent.

### ST02 / T01 — Prove SG05 acceptance and reverse assembly
Output: acceptance-to-evidence map and `Prompt → Task → Stage → Process → SG05 → G01` contribution proof.

### Acceptance
- primary run succeeds/attempts with no profile directory/cookies file and never asks for legacy preparation;
- primary Ozon failure remains typed failure, not browser launch;
- legacy path can be explicitly invoked and uses preserved legacy assets;
- regression detects accidental deletion/breakage of reserve entrypoints;
- automatic fallback switching is not introduced as a hidden requirement.

### Failure
- either side can only work by coupling them back together;
- legacy runtime smoke is required in an environment that cannot run a visible browser without a documented deferred evidence gate;
- Task boundary is widened instead of repairing decomposition.

---

## Dependency graph

```text
PR01 inventory + separation contract
        |
        v
PR02 explicit legacy capabilities
        |
        v
PR03 regression + closure
        |
        v
SG05
        |
        v
G01.A09 + contribution to A01/A08/A11
```

## Reverse-composition target

SG05 contributes exactly:
- G01.A09 fallback preservation;
- G01.A01/A11 by proving legacy preparation is not required for normal/repeated primary operation;
- G01.A08 by preserving manual WB dest capture only as optional support, never mandatory input.

No SG05 output is allowed to replace SG03/SG04 primary marketplace logic or SG06 run orchestration/persistence.
