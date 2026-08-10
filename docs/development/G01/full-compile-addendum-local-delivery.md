# G01 Whole-Contour Semantic Compilation Addendum — Local Delivery

Base report: `docs/development/G01/full-compile-report.md`
Added Task: #102 / `G01.SG06.PR03.ST04.T01`
Added Prompt: `prompts/work/G01-SG06/PR03-ST04-T01-C01-I01.md`
SG06 extension report: `docs/development/G01/SG06/local-delivery-extension.md`

## Active-generation delta

Original whole-contour report compiled 43 active Prompts. The operator subsequently added one additive SG06 operational-delivery Task.

Updated inventory:
- SG01: 6 active Prompts
- SG02: 6 active Prompts
- SG03: 7 active Prompts
- SG04: 8 active Prompts
- SG05: 6 active Prompts
- SG06: **11** active Prompts
- Whole G01: **44 active Prompts**

The original `full-compile-report.md` remains historical evidence of the 43-Prompt compile. This addendum is normative for the active 44-Prompt generation.

## New output
Task #102 provides a local Windows delivery/test loop:

```text
one double click
    -> no checkout: clone explicit repository/ref
    -> checkout exists: verify remote + fetch + safe fast-forward
    -> preserve local ignored secrets/profiles/results
    -> setup/refresh runtime only as required
    -> launch parser locally
```

## Cross-SG compatibility

### SG01–SG05
No new dependency. Task #102 transports/launches the composed implementation; it does not read or redefine ProductSet, CitySet, ProxyContext, WB/Ozon semantics or SG05 fallback credentials.

PASS.

### SG06 PR03
Task #102 depends on the accepted launch/runtime boundary from #98 and extends PR03 with an operator-facing local materialization path. It does not replace #98 scheduler-ready semantics.

PASS.

### Secret/state lifecycle
The local Git update contract explicitly preserves ignored/runtime-local `.env`, config, profiles/cookies, results, debug, venv/cache. It forbids destructive checkout wiping and embedded credentials.

This is compatible with SG05 personalized authenticated cookie preservation and all SG01/SG02 secret boundaries.

PASS.

### Git authority
GitHub/Git repository remains the durable code authority. The launcher may create a local checkout but may not create a divergent copied source tree. A dirty tracked checkout or wrong remote causes explicit stop rather than destructive reconciliation.

PASS.

### Write-scope / execution order
#102 should execute after #98 so it can invoke the accepted parser entrypoint. Its likely write scope is local-delivery `.bat`/helper/tests/docs and does not require concurrent editing of marketplace collectors. If it touches `install.bat` or `run_parser.bat`, serialize after #98 launcher changes.

PASS.

## Failure reverse check
New automatic failure conditions are covered:
- Git missing -> explicit local-delivery failure;
- auth failure -> explicit, no embedded PAT;
- wrong remote -> explicit stop;
- dirty tracked checkout -> `LOCAL_CHECKOUT_DIRTY`, no overwrite;
- destructive update/state deletion required -> `LOCAL_DELIVERY_SAFETY_MISMATCH`;
- ignored runtime secrets/profile/results lost -> Task #102 acceptance FAIL.

No pre-existing G01 failure condition loses enforcement.

## Reverse compile

```text
44 active Prompts
    -> Tasks
    -> Stages
    -> Processes
    -> SG01 + SG02(C02) + SG03 + SG04(C02) + SG05(C02) + SG06(11 Tasks)
    -> G01 Goal + local operator delivery/testing support
```

## Verdict

**`SEMANTIC_COMPILE_PASS (WHOLE G01 ACTIVE 44-PROMPT GENERATION)`**.

The new Task is additive and orthogonal to marketplace semantics. Controlled implementation remains authorized. Runtime WB/Ozon/legacy-auth/PG evidence gates remain unchanged and fail-closed.
