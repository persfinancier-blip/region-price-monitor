# prompt-17 — «Параметры подключения» tab: UI over the I/O backend (SPEC §5)

- **Branch:** `feat/connection-tab`
- **Commit type:** `feat:`
- **Docs:** [docs/SPEC-panel.md](../docs/SPEC-panel.md) §5 and §7, [ADR-0010](../docs/adr/0010-io-adapters.md)
  (backend this UI wraps), [ADR-0008](../docs/adr/0008-script-shell-separation.md),
  [ADR-0009](../docs/adr/0009-local-first-storage.md), [ADR-0011](../docs/adr/0011-local-settings-store.md),
  [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP.md](../docs/ROADMAP.md).
  New ADR: `docs/adr/0014-connection-tab.md`.

## Scope

Make the **«Параметры подключения» tab** real (SPEC §5, Фаза 8.4). The backend already exists from
`prompt-13` (ADR-0010): `app/io/` with `load_io_config` / `make_product_source` / `make_result_sink`,
the mapping table + `validate` / `preview`, and the canonical dictionary in `app/io/base.py`
(`PRODUCT_FIELDS`, `REGION_FIELDS`, `RESULT_FIELDS`, `REQUIRED_*`). This slice adds **only the panel
front-end that reads/writes `settings.io_config_path` (`io.json`)** — the panel is the input point,
the store is the local file (or DB params inside it). No adapter behaviour changes.

Follow SPEC §5's four sections as **left vertical sub-tabs** inside the «Параметры подключения» tab:

- **5.1 Источник** — where the SKU/region list comes from: `kind` (`json` | `csv` | `xlsx` | `db`) +
  its locator params (file path, sheet, range; or `database_url` + table names).
- **5.2 Маппинг входа** — the `{canonical → column}` table for **products** and **regions** (our
  fields on the left from `PRODUCT_FIELDS` / `REGION_FIELDS`, the source column on the right), with
  **preview** (first rows mapped) + **validation** (missing required / shifted columns).
- **5.3 Приёмник** — where results go: `kind` + params (path/sheet; or `database_url` + results table).
- **5.4 Маппинг выхода** — the `{canonical → column}` table for **results** (`RESULT_FIELDS`), with
  validation (and preview of the mapped output header).

**We do:**

1. **Thin connection script** (`app/scripts/connection.py`, standalone `python -m app.scripts.connection`
   and shell-delegated per ADR-0008): `load()` / `save(io_config)` for `io.json` (atomic temp+rename);
   `preview_source(endpoint, n=5)` — build the source, read the first rows, return them mapped to
   canonical fields via `app/io/mapping.preview`; `validate_source(endpoint)` / `validate_sink(endpoint)`
   — read the source header (csv first row / xlsx header row / db table columns) and run
   `mapping.validate` + `validate_known_fields`, returning all violations in one message; `columns(endpoint)`
   — the available source columns, so the UI can offer them and catch shifts. No business logic in the
   panel routes — they call straight through here.

2. **Expose public builders in the I/O factory** (the one allowed backend touch): add
   `build_product_source(endpoint)` / `build_result_sink(endpoint)` public wrappers over today's
   private `_build_*`, so the panel can preview/validate an **unsaved** endpoint from the form without
   writing the file first. No change to adapter behaviour or to `make_*`.

3. **Real «Параметры подключения» tab** (thin shell over `app/scripts/connection.py`):
   - `GET /tab/connection` renders the four vertical sub-tabs, pre-filled from the current `io.json`.
   - `POST /connection/source` and `POST /connection/sink` save the respective section (kind + params +
     mapping) back to `io.json`.
   - `POST /connection/preview` returns the mapped first rows + any validation errors for the posted
     (unsaved) source; a sink preview shows the resolved output header + validation.
   - Canonical field rows come from `app/io/base.py` (single source of truth) — required fields marked;
     the not-yet-final price fields (SPEC §9.5) simply appear as optional rows, no code change to add more.
   - Remove `connection` from `_PLACEHOLDER_TABS`; keep the other placeholders.

4. **DB credentials** — plain in `io.json` (no secret store, ADR-0009), **masked** in the rendered form
   (password in `database_url` shown masked; an empty password field on submit **keeps** the stored one,
   same pattern as proxies in the cities tab). Never print full `database_url` in logs.

5. **Docs (Russian):** `docs/adr/0014-connection-tab.md` — the tab as the input point over `io.json`,
   the four SPEC §5 sections, preview+validation, public factory builders, DB creds plain-local &
   masked, canonical §7 as the field source, price-field list still open (§9.5). Update
   `docs/SPEC-panel.md` §5 (delivered), `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (Фаза 8.4 delivered;
   next: general-profile editor / setup wizard), `DEVLOG.md`, `BACKLOG.md`.

**We do NOT:**
- **no setup wizard** — a later helper; here it's the plain form editor over `io.json`;
- **no changes to the I/O adapters' behaviour** — only add the public `build_*` wrappers;
- **no other tabs** (script-editor, logs), **no general-profile editor** — later slices;
- **no secret store / encryption** — DB creds plain-local, masked in UI/logs (ADR-0009);
- **do not change** the storage seam, cities store, cookies flow, collectors, or the measurement loop;
- no new marketplaces; no new canonical fields beyond `app/io/base.py`; money stays `Decimal`.

## Body (concrete files/steps)

1. `app/io/factory.py` — add public `build_product_source(endpoint)` / `build_result_sink(endpoint)`
   delegating to the existing `_build_*`; `make_*` unchanged.
2. `app/scripts/connection.py` — `load`/`save` (`io.json`, atomic); `columns`, `validate_source`,
   `validate_sink`, `preview_source`; header readers per kind (csv/xlsx/db) reusing `app/io` + `mapping`.
3. `app/panel/app.py` — real `GET /tab/connection`; `POST /connection/source`, `/connection/sink`,
   `/connection/preview`; delegate to `app/scripts/connection.py`; drop `connection` from placeholders.
4. `app/panel/templates/connection.html` — four vertical sub-tabs (Источник / Маппинг входа /
   Приёмник / Маппинг выхода), mapping tables built from `app/io/base.py` fields, preview + inline
   validation, reusing the existing CSS.
5. `cli.py` — a `connection` verb (`show` / `validate` / `preview`) mirroring the script.

## Constraints

- Model = Sonnet (pinned). Minimal read scope: `app/io/*`, `app/panel/*`, `app/scripts/connection.py`
  (new), `app/config.py`, `app/scripts/cities.py` (form/masking pattern reference). Don't rescan
  collectors/parser internals.
- **Local-first**: file backends (`json`/`csv`/`xlsx`) need no DB; the `db` path stays optional/lazy
  (parity with `make_*`). No `io.json` ⇒ the tab shows an empty/default form; nothing breaks.
- **Canonical §7 is the only field vocabulary** — the tables come from `app/io/base.py`; required
  fields flagged; validation surfaces missing/shifted/unknown columns in one message (SPEC §5.2/§5.4).
- **No secret store**: DB creds plain in `io.json`, **masked** in UI/logs; empty password on submit
  keeps the stored value. Atomic writes (temp+rename).
- Panel stays a **thin shell** (ADR-0008): routes call `app/scripts/connection.py`, no logic inline.
  Server-rendered forms; minimal JS in the existing style.
- Additive & back-compat: `make_*`, the adapters, and all earlier tests stay green.
- Code/comments/commits English; owner-facing docs Russian. Conventional Commits; one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green.
- New tests (no network; file backends need no DB):
  - `tests/test_connection_script.py` — `io.json` load/save round-trip (atomic); `validate_source`
    catches missing-required and shifted columns; `preview_source` returns canonical-mapped first rows
    for a csv and an xlsx source (tmp files); `columns` lists the header; db path behind the existing
    `TEST_DATABASE_URL` gate (skipped with no DB); masked `database_url`, empty-password-keeps-existing.
  - `tests/test_panel_connection.py` — `TestClient`: the tab renders the four sub-tabs pre-filled from
    `io.json`; `POST /connection/source` + `/connection/sink` persist; `POST /connection/preview`
    returns mapped rows and reports a shifted mapping as an error; no `io.json` ⇒ empty form, no crash.
  - `build_product_source` / `build_result_sink` build the same adapters as `make_*` for a given endpoint.
- Manual check (DEVLOG): `STORAGE_BACKEND=local`, panel → «Параметры подключения»: point the source at
  an `.xlsx`, map columns, preview shows canonical rows, a deliberately wrong column is flagged; set a
  csv sink + results mapping; `python -m app.scripts.export --preview` then reflects the saved config.
- `docs/adr/0014-connection-tab.md` + SPEC §5 / ARCHITECTURE / ROADMAP / DEVLOG / BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
