# Local Windows run — one double click

User-facing entrypoint: `START_PARSER.bat`.

## What it does

- keeps the Git checkout next to the BAT file by default;
- example: `C:\DEV\START_PARSER.bat` -> `C:\DEV\region-price-monitor`;
- first launch clones `persfinancier-blip/region-price-monitor` branch `work/g01-implementation`;
- later launches verify the expected origin/branch, fetch updates, and apply **fast-forward only**;
- tracked local edits are never overwritten automatically;
- ignored local state survives updates: `.env`, `parser/core/config.json`, `parser/core/local/`, profiles/cookies, debug, results and venv;
- `parser/core/local/products.json` is used through `RPM_PRODUCTS` so ordinary interactive SKU selection does not dirty the tracked `parser/core/products.json`;
- installer is called only when local runtime is missing or `install.bat` / `requirements.txt` changed;
- after successful sync/setup, `parser/run_parser.bat` is launched;
- `START_PARSER.bat` is intentionally ASCII-only to avoid Windows CMD encoding failures.

## First use

1. Put `START_PARSER.bat` into a convenient folder, for example `C:\DEV`.
2. Double-click it.
3. The first run creates `C:\DEV\region-price-monitor` when the BAT is in `C:\DEV`.
4. If Windows reports missing Git/Python, install the missing prerequisite and run it again.
5. The first run downloads the checkout and may spend time installing Python dependencies.
6. The parser menu opens after setup.

No manual `git clone`, `git pull`, archive copying, Docker or GitHub Actions are required.

## Every later use

Double-click the same `START_PARSER.bat`.

It checks Git state, downloads the newest commit from `work/g01-implementation` by safe fast-forward, refreshes dependencies only when needed, and starts the parser.

## Safety errors

- `LOCAL_CHECKOUT_DIRTY` — tracked source files have local edits. Nothing is overwritten; explicitly commit/stash/revert them before retrying.
- `LOCAL_CHECKOUT_WRONG_REMOTE` — local checkout points to another origin. Nothing is changed.
- `LOCAL_CHECKOUT_DIVERGED` — local commits/divergence exist. No destructive reset is attempted.
- `GIT_CLONE_FAILED` / `GIT_FETCH_FAILED` — check network and Git authentication. If the repository becomes private, use normal Git Credential Manager authentication; never put a PAT/password into the launcher.
- `GIT_NOT_FOUND` / `PYTHON_NOT_FOUND` — install the missing prerequisite and rerun.

For a non-technical operator: when one of the `LOCAL_CHECKOUT_*` errors appears, do not delete the local folder; send the error text/screenshot to the developer.

## Optional overrides

Advanced users may set:

- `RPM_LOCAL_ROOT` — alternate parent directory for the local checkout;
- `RPM_IMPLEMENTATION_BRANCH` — explicit branch to test instead of `work/g01-implementation`.

The launcher never silently follows an arbitrary branch.
