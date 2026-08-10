# G01.SG06.PR03.ST04.T01 — stale-checkout bootstrap repair

Issue: #102
Implementation PR: #103

## Observed operator failure

A Windows checkout created by an earlier launcher revision could exist locally before `tools/local_delivery.py` had been added to the implementation branch. The launcher checked for that helper **before any update**, so it stopped with `LOCAL_DELIVERY_HELPER_MISSING` and could not self-heal.

## Repair

`START_PARSER.bat` now contains a bounded bootstrap path used only when the helper is missing:

1. verify expected origin (accepting the canonical HTTPS URL with or without `.git`);
2. verify the checkout is already on the configured implementation branch;
3. fail closed on tracked dirty state;
4. `git fetch --prune origin <branch>`;
5. require local HEAD to be an ancestor of `origin/<branch>`;
6. apply `git merge --ff-only origin/<branch>`;
7. require `tools/local_delivery.py` to exist after the safe update;
8. hand off to the normal Python helper.

No `reset --hard`, `git clean`, branch switching, untracked deletion, secret deletion or silent conflict resolution is introduced.

The BAT remains ASCII-only / Windows-CRLF and defaults to a checkout beside the launcher, e.g. `C:\DEV\START_PARSER.bat -> C:\DEV\region-price-monitor`.

## Regression coverage

The repository test asserts that the Windows entrypoint remains ASCII-only and includes the stale-checkout bootstrap controls (`:bootstrap_helper`, fetch, ff-only merge, dirty/diverged guards).

## Runtime evidence still required

The operator should replace the prior BAT and rerun it against the already-created `C:\DEV\region-price-monitor` checkout. Successful bootstrap/update followed by setup/launch closes the observed desktop point-of-use failure.
