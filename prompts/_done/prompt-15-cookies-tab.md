# prompt-15 — Cookies: one-button collect with auto city-walk (SPEC §4)

- **Branch:** `feat/cookies-tab`
- **Commit type:** `feat:`
- **Docs:** [docs/SPEC-panel.md](../docs/SPEC-panel.md) §4 and §8, [ADR-0005](../docs/adr/0005-scraping-method-update.md),
  [ADR-0008](../docs/adr/0008-script-shell-separation.md), [ADR-0009](../docs/adr/0009-local-first-storage.md),
  [ADR-0011](../docs/adr/0011-local-settings-store.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md),
  [ROADMAP.md](../docs/ROADMAP.md). New ADR: `docs/adr/0012-cookie-collection-ux.md`.

## Scope

Make the **«Куки» tab** a working panel (SPEC §4). Owner UX decision (2026-07-23): **one button per
marketplace — «Авторизоваться и собрать» — you log in once, then the flow auto-walks the configured
cities, saving a cookie per city, pausing only when a captcha appears.** Symmetric button for **both
WB and Ozon**, but asymmetric under the hood: **Ozon** bakes the region into the cookie ⇒ a cookie
**per city**; **WB** takes the region from the proxy/request ⇒ **one session** (or a no-op) — not
per city. Runs on a **local machine with a visible browser** (Playwright Chromium); headless/Xvfb
warming on a bare Linux server stays the deferred open question (SPEC §9.2) — call it out, don't build it.

Cities and their per-marketplace proxies already come from the local store (`app/scripts/cities.py`,
ADR-0011) — the cookie flow consumes that effective view (warm-IP == fetch-IP per city where a proxy
is set).

**We do:**

1. **Symmetric warm, both marketplaces.** Extend `app/cookies/warm.py` so WB is a first-class target
   alongside Ozon (add a WB warm URL / login entry; `_MARKETPLACE_WARM_URL` covers both). Keep the
   existing `CookieWarmer`/`CookieStore`/`warm_if_stale` contracts; this is additive.

2. **Login-once + auto city-walk orchestration** — a `warm_all(marketplace, effective_cities)` flow:
   - Open one visible browser context; the operator logs in / passes the initial challenge **once**.
   - **Ozon:** iterate the cities from the store; for each, **auto-switch the delivery city** (via
     Ozon's region mechanism — cookie/param or the city selector), then save a **per-(ozon, city)**
     `CookieBundle`. Reuse the single logged-in context across cities. **Pause only on captcha:**
     auto-detect a challenge on the page and wait until it clears (poll), then continue — no console
     `input()`; the flow must be drivable without a terminal. Route each city through its effective
     proxy when one is set.
   - **WB:** warm **one** session bundle (region rides the proxy), not per city — same button, single
     pass. If WB currently needs no cookies, `warm_all` records that cleanly (a no-op session marker),
     so the button is still symmetric and honest.
   - Per-step timeout + a cooperative cancel/skip signal (so a stuck city doesn't hang the walk).

3. **Thin cookies script** (`app/scripts/cookies.py`, standalone `python -m app.scripts.cookies` and
   shell-delegated per ADR-0008): `collect(marketplace)` runs `warm_all` over the store's cities;
   `status()` lists stored bundles with **health** (per city/marketplace: warmed_at, age, valid /
   expiring / stale via `is_stale` + `ozon_cookie_ttl_hours`); `set_manual(marketplace, city, raw)`
   pastes/edits a cookie by hand; `clear(marketplace, city)` drops one bundle. Cookies stored locally
   under `settings.cookie_store_dir` (no secret store, ADR-0009); никаких кук в репозиторий.

4. **«Куки» tab in the panel** (thin shell over `app/scripts/cookies.py`, no logic in routes):
   - Two **«Авторизоваться и собрать»** buttons (WB, OZ) — symmetric — each launches `collect(mp)`
     as a background job that opens the visible browser locally; the tab shows **live progress**
     (current city, saved / waiting-on-captcha / done) by polling `status`.
   - A **health table** per city × marketplace: age + validity badge (валидна / истекает / протухла).
   - **Manual control:** view current cookie, paste/edit, save (`set_manual`), and clear.
   - An explicit note in-tab that collection needs a local visible browser (server warming later).
   - Replace the placeholder route for `cookies` with this real view; keep the other placeholders.

5. **Docs (Russian):** `docs/adr/0012-cookie-collection-ux.md` — one-button collect, login-once +
   auto city-walk, symmetric button / Ozon-per-city vs WB-single-session, captcha-pause via
   auto-detect (no console), local-visible-browser now + server headless deferred, cookies local &
   unencrypted (ADR-0009). `docs/SPEC-panel.md` §4 — mark the tab delivered (local); server warm =
   open question. `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (Фаза 8.3 delivered for local; next:
   connection-params UI 8.4, general-profile editor), `DEVLOG.md`, `BACKLOG.md`.

**We do NOT:**
- **no headless/Xvfb/remote-browser server warming** — deferred open question; local visible browser only;
- **no connection-params UI, no general-profile editor, no script-editor, no logs tab** — later slices;
- **no cookie encryption / secret store** — local single-user, plain under `cookie_store_dir` (ADR-0009);
- **do not change** the WB/Ozon collectors, the parser, the proxy layer, the storage/IO seams, or the
  cities store — only add the cookie-collection flow, its script, and the tab that drives them;
- no new marketplaces; CLI surface additive.

## Body (concrete files/steps)

1. `app/cookies/warm.py` — add WB as a warm target; factor `warm_all(marketplace, effective_cities)`
   (login-once, iterate cities, Ozon auto-switch + per-city save, WB single session, auto-detect
   captcha & wait, per-step timeout/cancel). Keep `warm`/`warm_if_stale` working.
2. `app/scripts/cookies.py` — `collect` / `status` (with health) / `set_manual` / `clear`; reads the
   cities store via `app/scripts/cities.py::list_effective`; standalone + shell entrypoints.
3. `app/panel/app.py` — real `GET /tab/cookies` view; `POST /cookies/{mp}/collect` (background job +
   in-process progress state), `GET /cookies/status` (poll), `POST /cookies/{mp}/{city}` (manual set),
   `POST /cookies/{mp}/{city}/clear`. Delegate to `app/scripts/cookies.py`; remove `cookies` from
   `_PLACEHOLDER_TABS`.
4. `app/panel/templates/cookies.html` — buttons, progress, health table, manual editor (reuse CSS).
5. `cli.py` — a `cookies` verb (collect/status/set/clear) mirroring the script.

## Constraints

- Model = Sonnet (pinned). Minimal read scope: `app/cookies/*`, `app/scripts/cookies.py` (new),
  `app/scripts/cities.py`, `app/panel/*`, `app/config.py`, `app/enums.py`, `app/models.py`. Don't
  rescan collectors/parser internals.
- **Local-first, visible browser**: the collect flow opens a real local Chromium; it must be
  **panel-drivable** (auto-detect captcha and wait/poll — never block on terminal `input()`).
  Per-step timeout + cancel so the walk can't hang.
- **Ozon = cookie per city; WB = one session** (region via proxy). Symmetric button, asymmetric
  under the hood. Route each city through its effective proxy where set (warm-IP == fetch-IP).
- **No secret store**: cookies plain under `cookie_store_dir`, gitignored; never printed in full in
  logs (mask/trim); proxy creds masked as elsewhere.
- Additive: existing `warm`/`warm_if_stale`, collectors, and all earlier tests stay green.
- Code/comments/commits English; owner-facing docs (ADR/SPEC/ARCHITECTURE/ROADMAP/DEVLOG/BACKLOG)
  Russian. Conventional Commits; one vertical slice = one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green.
- New tests (no network, no real browser — inject a **stub warmer**):
  - `tests/test_cookies_script.py` — `collect` walks the store's cities and saves a bundle per Ozon
    city and a single WB session via a stub warmer; `status` reports health (valid / expiring / stale
    boundaries via `is_stale`); `set_manual` / `clear` round-trip through `cookie_store_dir` (tmp).
  - `tests/test_panel_cookies.py` — `TestClient`: the Cookies tab renders buttons + health table;
    `POST /cookies/{mp}/collect` starts a job (stubbed) and `GET /cookies/status` reflects progress;
    `POST /cookies/{mp}/{city}` sets a manual cookie; clear drops it.
  - The live visible-browser path is exercised only under an opt-in gate (e.g. `MANUAL=1`), documented
    in DEVLOG, and **excluded from CI**.
- Manual check (documented in DEVLOG): on local Windows, `STORAGE_BACKEND=local`, start `panel`, open
  «Куки», press «Авторизоваться и собрать» for Ozon — log in once, the flow walks the cities and saves
  a cookie per city, pausing on captcha; the health table shows fresh cookies; WB does its single pass.
- `docs/adr/0012-cookie-collection-ux.md` + SPEC §4 / ARCHITECTURE / ROADMAP / DEVLOG / BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
