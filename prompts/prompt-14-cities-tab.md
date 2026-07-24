# prompt-14 — Cities: functional add/configure block (SPEC §3), local settings store

- **Branch:** `feat/cities-config`
- **Commit type:** `feat:`
- **Docs:** [docs/SPEC-panel.md](../docs/SPEC-panel.md) §3, [ADR-0008](../docs/adr/0008-script-shell-separation.md),
  [ADR-0009](../docs/adr/0009-local-first-storage.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md),
  [ROADMAP.md](../docs/ROADMAP.md). New ADR: `docs/adr/0011-local-settings-store.md`.
  **Supersedes** the previously-planned `prompt-14` (setup wizard) — that moves later; this makes the
  panel actually usable first.

## Scope

Owner feedback (2026-07-23): the panel is a read-only shell — every tab is a placeholder and the
Dashboard lets you configure nothing. **Fix the priority: the panel must be a working input point.**
The settings model is fixed: **settings live locally in a config file (or DB); the panel is just the
front-end that reads/writes them.** This slice delivers the first functional piece — the **«Города»
block on the Dashboard** (SPEC §3): add a city, and per city configure **WB** and **Ozon** with the
**inherit-general / override-locally** model and an **enable/disable** toggle — all persisted to a
**local settings file** and honoured by the measurement loop.

Local mode unblocks this: no secret store (ADR-0009), and the current placeholder theme is fine — the
brand book is cosmetic and not a blocker.

**We do:**

1. **Local settings store for cities** — a new flat JSON file (path from a new
   `settings.city_config_path = "config/cities.json"`), atomic writes (temp+rename), no secrets store.
   Shape:
   ```json
   {
     "defaults": {
       "wb":   { "enabled": true, "proxy": null, "interval_min": 360 },
       "ozon": { "enabled": true, "proxy": null, "interval_min": 360 }
     },
     "cities": [
       { "code": "msk", "name": "Москва", "geo": { "ozon": "..." },
         "wb":   { "mode": "inherit" },
         "ozon": { "mode": "override", "enabled": true, "proxy": "http://…", "interval_min": 120 } }
     ]
   }
   ```
   `mode` is `inherit` | `override`; an `override` carries `enabled` / `proxy` / `interval_min`.
   **Effective** per (city, marketplace) = `defaults[mp]` when `inherit`, else the override fields.
   `enabled: false` removes that (city, marketplace) from the work set entirely.

2. **A thin cities script** (`app/scripts/cities.py`, standalone-runnable `python -m app.scripts.cities`
   and shell-delegated per ADR-0008): `load()` / `save()` the config atomically; `list_effective()`
   (defaults merged with per-city overrides, disabled pairs dropped); `add_city(code, name, geo)`;
   `set_marketplace(code, mp, mode, *, enabled, proxy, interval_min)`; `set_enabled(code, mp, on)`;
   `remove_city(code)` (**deactivate / drop from config — never hard-delete history**). Proxy values
   **masked** in any printed/logged output; the real value is kept in the file.

3. **Wire the engine through it.** `app/scripts/control_panel.py::run` builds its `CitySettings`
   from `cities.list_effective()` instead of `parse_proxy_map(settings.proxy_map_json)`: proxy per
   city comes from the effective settings, and a marketplace disabled for a city is excluded from
   `pairs`/`cities`. Extend `CitySettings` to carry effective per-marketplace settings (proxy +
   enabled). **Back-compat:** with **no** `config/cities.json`, seed it once from the current
   `regions` store (code/name/geo) + `proxy_map_json`/interval settings, so existing behaviour is
   preserved; `proxy_map_json` stays supported as a seed/fallback.

4. **Make the Dashboard «Города» block interactive** (server-rendered forms, matching the current
   panel style; the panel stays a thin shell delegating to `app/scripts/cities.py`, no business logic
   in routes):
   - **Add city** — a small form (code, name, optional Ozon region hint for `geo`) → `POST /cities`
     → creates the city (both marketplaces `inherit` by default).
   - **Per-city, per-marketplace** sub-block (WB and OZ) with a **«Наследует общее / Локально»**
     control; in «Локально» — fields for proxy, interval, and an enable/disable toggle →
     `POST /cities/{code}/{mp}`. Proxy shown **masked**; an empty proxy field on submit **keeps** the
     stored value (don't blank it).
   - **Enable/disable** a marketplace for a city → same endpoint / a dedicated toggle.
   - **Remove city** → `POST /cities/{code}/delete` (deactivate; history untouched).
   - Show the general **defaults** (WB/OZ) read-only in this block so «inherit» is meaningful — the
     full **editor** for the general profile (and the global площадка on/off) is the **next** slice.
   - After each mutation, re-render the block from the file (redirect back to `/`).

5. **Config + docs.** `app/config.py` + `.env.example`: add `city_config_path`. Ship
   `config/cities.example.json`. `docs/adr/0011-local-settings-store.md` — the local settings store,
   panel-as-input-point, inherit/override + enable model, seed/back-compat, no secret store.
   `docs/SPEC-panel.md` §3 — the «Города» block is now functional (general-profile editor + global
   toggle = next slice). `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (Фаза 8.2 delivered; next: general
   profile editor, cookies 8.3, connection-params UI 8.4), `DEVLOG.md`, `BACKLOG.md`.

**We do NOT:**
- **no cookies tab, no connection-params UI, no script-editor, no logs tab** — separate slices;
- **no full general-profile editor and no global площадка on/off toggle** — next slice; here defaults
  are shown read-only and seeded;
- **no secret store / encryption** — proxy creds live in the plain local config (masked in UI/logs);
- **do not change** collector/proxy/cookie/parser logic, the storage seam, the I/O adapters, or the
  measurement algorithm — only where the work set reads per-city settings, route it through the new
  store;
- no new marketplaces; no new canonical fields; CLI command surface stays additive.

## Body (concrete files/steps)

1. `app/config.py`, `.env.example`, `config/cities.example.json` — `city_config_path` + documented shape.
2. `app/scripts/cities.py` — the store + effective-resolution + CRUD script (thin, standalone + shell).
3. `app/scripts/control_panel.py::run` — build `CitySettings` from `cities.list_effective()`; extend
   `CitySettings` with effective per-marketplace proxy/enabled; drop disabled (city, mp) pairs.
   Keep `format_report`/`show` output stable (proxy still masked).
4. `app/panel/app.py` — add `POST /cities`, `POST /cities/{code}/{mp}`, `POST /cities/{code}/delete`;
   the Dashboard context already carries `cities` — enrich it with per-marketplace inherit/override +
   enabled + masked-proxy view; delegate all writes to `app/scripts/cities.py`.
5. `app/panel/templates/dashboard.html` — replace the read-only «Активные города» table with the
   interactive block (collapsed row + expandable WB/OZ sub-blocks + add-city form), reusing existing
   CSS tokens; add a read-only defaults line.
6. `cli.py` — a `cities` verb mirroring the script (list/add/set/remove).

## Constraints

- Model = Sonnet (pinned). Minimal read scope: `app/scripts/control_panel.py`, `app/panel/*`,
  `app/storage/*`, `app/config.py`, `app/proxy/static.py`, `app/enums.py`. Don't rescan collectors/
  parser internals.
- **Local-first**: everything works with `STORAGE_BACKEND=local` and no DB; the cities store is a
  flat file with **atomic** writes. No secret store — proxy creds plain in the file, **masked** in
  every printed/logged/HTML output (empty proxy field on edit = keep existing).
- **Back-compat**: no `config/cities.json` ⇒ seed from `regions` + `proxy_map_json`/intervals; all
  earlier tests stay green; the Dashboard, `run-once`, metrics, and `control-panel show` behave the
  same when nothing is overridden.
- Panel stays a **thin shell** (ADR-0008): routes call `app/scripts/cities.py`, no logic inline.
  Server-rendered forms; keep JS minimal and in the existing style.
- Code/comments/commits English; owner-facing docs (ADR/SPEC/ARCHITECTURE/ROADMAP/DEVLOG/BACKLOG)
  Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green.
- New tests (no network; local backend, no DB):
  - `tests/test_cities_store.py` — config load/save round-trip (atomic); `list_effective()` resolves
    inherit vs override and **drops disabled** (city, marketplace) pairs; add/set/enable/remove;
    seed-from-regions when the file is absent.
  - `tests/test_panel_cities.py` — FastAPI `TestClient`: the Dashboard renders the interactive block;
    `POST /cities` adds a city; `POST /cities/{code}/{mp}` sets override / inherit / enabled and the
    file reflects it; masked proxy on render; empty-proxy submit keeps the stored value;
    `POST /cities/{code}/delete` deactivates.
  - `control_panel.run` honours the store: an overridden proxy appears for that city; a disabled
    marketplace is absent from `pairs`/`cities`.
- Manual check (documented in DEVLOG): with `STORAGE_BACKEND=local`, start `panel`, add a city, set an
  Ozon proxy override and disable WB for one city — the changes persist in `config/cities.json` and a
  subsequent `control-panel show` / `run-once` reflects them.
- `docs/adr/0011-local-settings-store.md` records the store + inherit/override/enable model +
  panel-as-input-point + seed/back-compat + no-secret-store; `docs/SPEC-panel.md` §3, ARCHITECTURE,
  ROADMAP (8.2 done; next slices listed), DEVLOG, BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
