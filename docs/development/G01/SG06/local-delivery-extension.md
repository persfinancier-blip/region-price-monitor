# G01.SG06 local-delivery extension — Task #102

Parent: Issue #36
Process: #90 / `G01.SG06.PR03`
Task: #102 / `G01.SG06.PR03.ST04.T01`
Prompt: `prompts/work/G01-SG06/PR03-ST04-T01-C01-I01.md`

## Reason
After the original ten-Task SG06 vertical compiled, the operator added an explicit delivery/testing requirement: one Windows double-click artifact must create the local Git checkout on first use, update it safely on later uses, and launch the parser so cloud-developed code can be validated locally without manual Git commands.

This is an additive operational-delivery responsibility. It does not change marketplace, proxy, persistence or fallback semantics.

## Stage contract — PR03.ST04

### Input
- accepted PR03.ST02 local/parser launch interface (#98);
- repository URL and explicit implementation branch/ref;
- existing Windows delivery assets (`install.bat`, `parser/run_parser.bat`, `parser/core/requirements.txt`).

### Output
One double-click Windows bootstrap/sync launcher that:
1. on first run verifies Git and clones the expected repository/ref into a predictable local directory;
2. prepares/reuses the supported runtime setup and starts the parser;
3. on later runs verifies expected repository/remote, fetches the configured ref and updates only by safe fast-forward/switch semantics;
4. never uses destructive `reset --hard`, checkout wiping, untracked-file deletion or silent overwrite of tracked local work;
5. stops explicitly with `LOCAL_CHECKOUT_DIRTY` when tracked local edits would be overwritten;
6. preserves ignored/runtime-local `.env`, config, profiles/cookies, results, debug, venv/cache and other secret/state material;
7. embeds no PAT/password/cookie/proxy credential and prints no secret;
8. uses normal authenticated Git/Git Credential Manager behavior if repository access later becomes private;
9. keeps Git checkout as the code source of truth, not a copied shadow tree.

### Evidence
Prefer deterministic tests against a temporary local/bare Git remote covering:
- first clone;
- subsequent fast-forward update;
- no-change launch;
- dirty tracked checkout stop;
- wrong remote/repository stop;
- ignored runtime-state preservation.

## Virtual execution

Expected implementation is small and repository-local: a root/operator-facing `.bat` (name implementation-defined), possibly a helper script if necessary, plus tests/instructions. It composes with existing installer/launcher instead of duplicating dependency knowledge.

### Safety simulation
- no checkout exists -> clone -> setup -> launch: PASS;
- checkout clean, remote advanced -> fetch/fast-forward -> launch: PASS;
- checkout clean, remote unchanged -> launch without destructive rebuild: PASS;
- tracked local edit conflicts with update -> `LOCAL_CHECKOUT_DIRTY`, no overwrite: PASS fail-closed;
- ignored `profiles/`, `.env`, config/results exist -> Git update leaves them intact: PASS;
- remote identity mismatch -> stop, do not pull foreign code: PASS fail-closed;
- authentication fails -> human-readable Git auth failure, no embedded PAT: PASS fail-closed.

## Reverse composition

`Prompt #102 -> Task #102 -> PR03.ST04 -> PR03 -> SG06 -> G01 operational validation support`.

No existing G01.A01–A12 semantic acceptance is weakened. This extension improves delivery/testability only. It adds one SG06 acceptance clause: cloud-developed implementation can be materialized and updated locally with one double-click without destructive state loss.

## Verdict

**`SEMANTIC_COMPILE_PASS (SG06 local-delivery extension)`**.

SG06 active Task count becomes 11 and active Prompt count becomes 11. Whole-G01 active Prompt total becomes 44; see `docs/development/G01/full-compile-addendum-local-delivery.md`.
