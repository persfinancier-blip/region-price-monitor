# prompt-13 — Source/sink adapters: CSV / Excel / DB + field mapping (SPEC §5, §7)

- **Branch:** `feat/io-adapters`
- **Commit type:** `feat:`
- **Docs:** [ADR-0009](../docs/adr/0009-local-first-storage.md) (this is the "source/sink each
  local-or-DB + mapping" slice it named as **next**), [docs/SPEC-panel.md](../docs/SPEC-panel.md)
  §5 and §7, [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [ROADMAP.md](../docs/ROADMAP.md).
  New ADR: `docs/adr/0010-io-adapters.md`.

## Scope

Deliver the **configurable I/O layer** promised by ADR-0009 and SPEC §5: the product/region
**source** and the results **sink** each become **CSV / Excel / DB**, driven by a **field-mapping
table** that maps our **canonical fields** (SPEC §7) to the source's columns (sheet+column) or the
DB's columns (table+column), and back out for results. This is the **backend** the panel's
"Параметры подключения" tab (Фаза 8.4) will later wrap — build the engine + config + files here,
**not** the UI and **not** the setup wizard.

The canonical vocabulary is fixed by **SPEC §7** and must be the single internal dictionary both
directions map through:
`marketplace, sku, url, name, region, price, price_no_card, price_card, currency, availability,
measured_at, status`.
Input (product/region list) uses the reference subset (`marketplace, sku, url, name` for products;
`region`/`code, name, geo` for regions); output (results) uses the full set. The mapping table is
**data-driven** so the not-yet-finalised price-field list (SPEC §9.5) can grow later without code
changes — note that open question, don't try to resolve it here.

**We do:**

1. **I/O seam** — a new `app/io/` package with Protocols and a factory, mirroring the `app/storage/`
   seam style:
   - `ProductSource` — `read_products() -> list[dict]` / `read_regions() -> list[dict]` yielding
     rows already keyed by **canonical** field names (mapping applied inside the adapter).
   - `ResultSink` — `write_snapshots(rows: list[dict]) -> int` consuming **canonical**-keyed result
     rows and writing them mapped to the target's columns.
   - `make_product_source(settings)` / `make_result_sink(settings)` pick the impl by config
     (`kind`: `json` | `csv` | `xlsx` | `db`).

2. **Adapters** (`kind`):
   - **`json`** — the existing local-JSON shape stays the **default** and keeps working unchanged
     (back-compat: today's `control-panel import-products/import-regions <file>` behaviour is
     preserved; JSON needs no mapping — keys are already canonical).
   - **`csv`** — read/write `.csv`; mapping is `canonical -> column header`.
   - **`xlsx`** — read/write `.xlsx` via **openpyxl** (add dependency); config: `path`, `sheet`,
     optional A1 `range`; mapping is `canonical -> column` (header name or letter).
   - **`db`** — read a source table / write a results table over a SQL connection (reuse the
     SQLAlchemy stack already in the repo; connection params in plain local config per ADR-0009 —
     **no secret store**); mapping is `canonical -> table column`. DB deps stay **optional** —
     importing `app.io.db` must not be required when `kind` is a file backend, exactly like the
     storage `postgres` path.

3. **Mapping + validation + preview** (`app/io/mapping.py`):
   - A declarative **mapping table** `{canonical_field: source_locator}` loaded from local config
     (a JSON/TOML file under the config dir, e.g. `config/io.json`; path from settings). Separate
     `source` (products/regions in) and `sink` (results out) sections.
   - **`validate(mapping, sample)`** — flags unknown canonical fields, missing required fields
     (`marketplace, sku, url, name` for product input; `sku, region, price, measured_at, status`
     for result output), and columns present in the mapping but absent in the source header (so a
     shifted sheet is caught, SPEC §5.2).
   - **`preview(source, n=5)`** — return the first N mapped rows for a dry-run sanity check
     (the panel/wizard will render this later).

4. **Wire into the scripts (thin shells, ADR-0008):**
   - `app/scripts/control_panel.py`: `import-products` / `import-regions` gain the ability to read
     through `make_product_source(settings)` (configured source) **in addition to** the current
     explicit-file JSON path. Default/unconfigured behaviour is unchanged.
   - **New `app/scripts/export.py`** (`python -m app.scripts.export`, and an `export` CLI verb in
     the thin `cli.py` dispatcher): read `price_snapshots` (+ joined product/region) from the
     storage seam, build canonical result rows, and write them through `make_result_sink(settings)`.
     Standalone-runnable and shell-delegated like the other scripts. A `--preview` flag prints the
     first rows instead of writing.

5. **Config** (`app/config.py` + mirror `.env.example`): `io_config_path: str = "config/io.json"`
   (declares source/sink `kind` + locators + mapping). Keep everything optional with safe defaults
   (no `io.json` ⇒ `json` source + no sink configured ⇒ `export` is a no-op that says so). Ship a
   `config/io.example.json` documenting the shape for csv/xlsx/db.

6. **Docs (Russian):** `docs/adr/0010-io-adapters.md` — the I/O seam, the four `kind`s, the mapping
   table + validation/preview, canonical §7 dictionary as the pivot, DB creds in plain local config
   (no secret store), price-field list still open (§9.5) but the table is extensible.
   `docs/ARCHITECTURE.md` — add the I/O seam next to the storage seam. `docs/SPEC-panel.md` — mark
   §5.1–5.4 backend as delivered by this slice (UI = Фаза 8.4, wizard = prompt-14).
   `docs/ROADMAP.md` — record this slice; next = `prompt-14` (setup helper/wizard over this).
   `DEVLOG.md` + `BACKLOG.md` updated.

**We do NOT:**
- **no setup wizard / mapping UI** — that is `prompt-14`; here mapping lives in a config file only;
- **no panel tab 8.4 UI** and no other panel tabs (8.2/8.3/8.5);
- **no new canonical fields** beyond SPEC §7 and **no attempt to finalise §9.5** — keep the table
  data-driven and note the open question;
- **do not change** collector / proxy / cookie / parser logic, the measurement loop, the storage
  seam behaviour, or observability — only add the read-in / write-out edges;
- **do not remove or break** the current JSON import path; this is additive;
- no new marketplaces; money stays `Decimal` (serialised as string, never float); no secret store.

## Body (concrete files/steps)

1. `app/io/base.py` — `ProductSource` / `ResultSink` Protocols; canonical field constants (single
   source of truth, aligned to SPEC §7); a `SourceLocator`/`Mapping` type alias.
2. `app/io/mapping.py` — load mapping config, `validate()`, `preview()`; header/column resolution
   helpers (name or letter for xlsx).
3. `app/io/json_source.py` — canonical-keyed passthrough (today's shape); the default.
4. `app/io/csv_io.py` — csv source + sink (`csv` module).
5. `app/io/xlsx_io.py` — xlsx source + sink (**openpyxl**); sheet/range aware.
6. `app/io/db_io.py` — SQL source + sink over SQLAlchemy (optional import); connection from config.
7. `app/io/factory.py` — `make_product_source(settings)` / `make_result_sink(settings)` by `kind`.
8. `app/scripts/control_panel.py` — route `import-*` through the configured source when set; keep
   the explicit-file JSON path and the printed `imported <n> / updated <n>` output identical.
9. `app/scripts/export.py` — new standalone script + `cli.py` `export` verb; `--preview`.
10. `app/config.py`, `.env.example`, `config/io.example.json` — config surface + documented shape.
11. `pyproject.toml` — add `openpyxl`; keep DB extras optional.

## Constraints

- Model = Sonnet (pinned). Minimal read scope: `app/storage/*`, `app/scripts/control_panel.py`,
  `app/scripts/report.py`, `app/models.py`, `app/config.py`, `cli.py`. Don't rescan collectors/
  proxy/parser internals.
- **Canonical §7 is the only internal vocabulary**; both directions map through it. Required-field
  validation as specified above. Unknown/missing columns are a clear error, not a silent skip.
- **File backends need no DB and no network**; `db` adapter import is lazy/optional (parity with the
  storage `postgres` path). Local-first defaults: no `io.json` ⇒ JSON source, no sink.
- Back-compat: the existing JSON `import-products`/`import-regions` path and its stdout are
  unchanged; all earlier tests stay green (adapt only wiring, not assertions).
- Money stays `Decimal` (string on the wire); `measured_at` ISO-8601; `currency` defaults `RUB`.
- **No secret store** — DB/source creds in plain local config; still **masked** in any logged/printed
  output.
- Code/comments/commits English; owner-facing docs (ADR/ARCHITECTURE/SPEC/ROADMAP/DEVLOG/BACKLOG)
  Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green.
- New tests (no network; file backends need no DB):
  - `tests/test_io_mapping.py` — mapping load, `validate()` catches unknown/missing/shifted columns,
    `preview()` returns mapped rows.
  - `tests/test_io_csv.py` / `tests/test_io_xlsx.py` — round-trip: a source file with a non-canonical
    header maps into canonical product/region rows; a sink writes canonical result rows to the mapped
    columns (tmp files); `Decimal` prices survive as strings.
  - `tests/test_io_json_backcompat.py` — the default JSON source reproduces today's import exactly.
  - DB adapter tested behind the existing `TEST_DATABASE_URL` gate; skipped with no DB.
- `python -m app.scripts.export --preview` prints the first mapped result rows; with a sink
  configured it writes them; with none configured it exits cleanly stating no sink is set.
- With `kind: xlsx`/`csv` source configured, `control-panel import-products` populates the store
  through the mapping; with no `io.json`, the JSON path behaves exactly as before.
- `docs/adr/0010-io-adapters.md` records the seam, `kind`s, mapping/validation/preview, canonical §7
  pivot, no-secret-store, and the open §9.5 field list; `docs/ARCHITECTURE.md`, `docs/SPEC-panel.md`
  (§5 backend delivered, UI=8.4, wizard=prompt-14), `docs/ROADMAP.md`, `DEVLOG.md`, `BACKLOG.md`
  updated.
- Merged into `main` via PR with the DoD gate green.
