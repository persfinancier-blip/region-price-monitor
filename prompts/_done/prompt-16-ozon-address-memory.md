# prompt-16 — Ozon region by remembered address + auto-repair (revises ADR-0012)

- **Branch:** `feat/cookies-address-memory`
- **Commit type:** `feat:`
- **Docs:** [ADR-0012](../docs/adr/0012-cookie-collection-ux.md) (**revised here**),
  [ADR-0005](../docs/adr/0005-scraping-method-update.md), [ADR-0008](../docs/adr/0008-script-shell-separation.md),
  [ADR-0009](../docs/adr/0009-local-first-storage.md), [ADR-0011](../docs/adr/0011-local-settings-store.md),
  [docs/SPEC-panel.md](../docs/SPEC-panel.md) §4/§8, [ROADMAP.md](../docs/ROADMAP.md).
  New ADR: `docs/adr/0013-ozon-address-memory.md` (revises ADR-0012).

## Scope

Fix the Ozon region mechanism in `warm_all`. The current step `_switch_ozon_city` re-visits
`https://www.ozon.ru/?city=<name>` — that is **wrong**: Ozon does **not** take the region from a
`?city=` query. Ozon bakes the region into the **cookie set** (the `__Secure-*` / `abt_data` family),
and that cookie is written when the operator **picks a delivery address** in the UI. A free-form city
name cannot be reliably mapped to Ozon's canonical location.

Owner decision (2026-07-24): **don't guess the mapping — capture the operator's real choice once and
remember it, then auto-repair.**

- **First-time setup — guided, per city, remembering the chosen address.** The operator logs in once,
  then for each Ozon city picks the real delivery address in the browser; we save the resulting
  per-(ozon, city) cookie **and remember the chosen address** (a label + whatever stable marker is
  capturable) with that city's cookie record.
- **Refresh — automatic, by the remembered address.** When a city's cookie goes stale, the flow
  re-opens the logged-in browser, **auto-selects the remembered saved address** from the account's
  address book, and saves a fresh cookie. The browser only pauses for a **captcha** or a needed
  re-login (auto-detected, polled — never a console `input()`).

WB is unchanged: single `_session` bundle, region via proxy; the «Собрать» button stays symmetric.

**We do:**

1. **Remember the chosen address.** Add an optional `address_label: str | None` to `CookieBundle`
   (`app/cookies/base.py`), persisted with the bundle (the remembered Ozon delivery address for that
   city). WB's `_session` bundle leaves it `None`. Keep back-compat when loading older bundles
   (missing field ⇒ `None`).

2. **Replace `?city=` with capture-and-select** in `app/cookies/warm.py`:
   - **Guided capture** (first-run / re-configure): navigate Ozon, let the operator select/confirm
     the delivery address for the city in the visible browser, then read `storage_state` and the
     chosen address label; save the per-(ozon, city) bundle with `address_label` set. Detect
     "address chosen / page ready" defensively (poll, with the existing `step_timeout_s` + `cancel`).
   - **Auto-select** (refresh): with a remembered `address_label`, drive Ozon to pick that saved
     address from the account's address list (match by label); on success save the fresh cookie. If
     the address isn't found or a login is required, fall back to a guided pause (surface the browser)
     rather than silently failing.
   - Remove `_switch_ozon_city`'s `?city=` URL hack. Keep `_looks_like_captcha` / `_wait_out_captcha`,
     per-step timeout, `CancelToken`, `ProgressReporter`, and the `launch_browser` test seam.

3. **Two clear flows in the cookies script** (`app/scripts/cookies.py`):
   - `collect(marketplace)` — guided: walks cities that have **no** remembered address (or all, when
     forced), capturing address + cookie. (Existing symmetric-button entry.)
   - `refresh(marketplace)` — auto: for cities whose cookie is **stale** and that **have** a
     remembered address, re-warm by auto-selecting it; guided fallback only when needed.
   - `status()` gains the remembered `address_label` per Ozon city next to the health verdict.
   - `set_manual` / `clear` stay; `set_manual` may also set an address label.

4. **Panel «Куки» reflects the model** (thin shell, no logic in routes):
   - Per Ozon city show: remembered address (or «адрес не задан»), cookie health, and actions
     **«Настроить/перенастроить адрес»** (guided) and **«Обновить»** (auto-repair). The main
     «Авторизоваться и собрать» button = guided for unremembered cities + fresh capture.
   - A **«Обновить протухшие»** action runs `refresh` for all stale-with-address cities.
   - Keep the live-progress polling and the local-visible-browser note.

5. **Docs (Russian):** `docs/adr/0013-ozon-address-memory.md` — why `?city=` was wrong (region lives
   in the cookie, set by choosing an address), the capture-once-remember model, auto-repair by saved
   address, guided fallback, WB unchanged; **marks ADR-0012 revised in part**. Update
   `docs/SPEC-panel.md` §4 (cookie region = remembered address, not name-mapping),
   `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `DEVLOG.md`, `BACKLOG.md`.

**We do NOT:**
- **no free-name → Ozon-canonical mapping / guessing** — that was the bug; capture the real choice;
- **no headless/server auto-repair** — repair needs the visible local browser; the bare-Linux-server
  case stays the deferred open question (SPEC §9.2). `warm_if_stale` inside collector runs is **not**
  turned into a silent headless re-warm; auto-repair is an explicit panel/CLI action;
- **no cookie/secret encryption** — cookies + address label local & gitignored (ADR-0009);
- **do not change** the WB/Ozon collectors, parser, proxy layer, storage/IO seams, or the cities
  store schema beyond reading it; WB single-session behaviour is unchanged;
- no new marketplaces; CLI surface additive.

## Body (concrete files/steps)

1. `app/cookies/base.py` — add `address_label: str | None = None` to `CookieBundle`; tolerant load.
2. `app/cookies/warm.py` — drop `_switch_ozon_city` (`?city=`); add `_capture_ozon_address` (guided)
   and `_select_saved_address` (auto by label); thread `address_label` through `WalkCity`/
   `WalkStepResult`/`_save_bundle`. Keep captcha-wait, timeout, cancel, progress, `launch_browser`.
3. `app/scripts/cookies.py` — add `refresh()`; `collect()` skips cities that already have a remembered
   address unless forced; `status()` surfaces the label; wire a `refresh` CLI verb.
4. `app/panel/app.py` + `templates/cookies.html` — per-city address + actions, «Обновить протухшие».
5. `cli.py` — add the `cookies refresh` verb.

## Constraints

- Model = Sonnet (pinned). Minimal read scope: `app/cookies/*`, `app/scripts/cookies.py`,
  `app/scripts/cities.py`, `app/panel/*`, `app/config.py`, `app/enums.py`, `app/models.py`.
- **Local, visible browser**; panel-drivable (auto-detect captcha/login, poll — never console
  `input()`); per-step timeout + cancel so a stuck city can't hang the walk.
- **Ozon = remembered address per city; WB = single `_session`** (unchanged). The exact Ozon
  address-book selection (DOM/API) is empirically uncertain — implement it **defensively** behind the
  captcha-wait/timeout/cancel framework, with a guided fallback; the live browser path stays gated
  (`MANUAL=1`) and **excluded from CI**, validated manually (note in DEVLOG).
- **No secret store**; cookies + address label local, gitignored; never print full cookie contents.
- Additive & back-compat: older bundles (no `address_label`) load fine; existing `warm`,
  `warm_if_stale`, collectors, and all earlier tests stay green.
- Code/comments/commits English; owner-facing docs Russian. Conventional Commits; one PR.

## Definition of Done

- `scripts/dod.sh` (ruff + mypy strict + pytest) exits green.
- New/updated tests (no network, no real browser — inject a **stub browser/warmer**):
  - `tests/test_cookies_address.py` — guided capture records `address_label` + cookie per Ozon city;
    `refresh` auto-selects the remembered label and re-saves only stale-with-address cities; a city
    with no remembered address is skipped by `refresh` (guided fallback path exercised via stub);
    WB still saves a single `_session` bundle with `address_label=None`.
  - `tests/test_panel_cookies.py` updated — the tab shows the remembered address; «Обновить протухшие»
    triggers `refresh` (stubbed) and status reflects it.
  - `CookieBundle` back-compat: a stored bundle without `address_label` loads as `None`.
  - The live visible-browser path stays behind `MANUAL=1`, excluded from CI.
- Manual check (DEVLOG): local Windows, `STORAGE_BACKEND=local`, panel → «Куки»: first run picks an
  address per Ozon city (remembered), later «Обновить протухшие» refreshes them automatically, browser
  surfacing only on captcha; WB does its single pass.
- `docs/adr/0013-ozon-address-memory.md` records the revision and marks ADR-0012 partly superseded;
  SPEC §4, ARCHITECTURE, ROADMAP, DEVLOG, BACKLOG updated.
- Merged into `main` via PR with the DoD gate green.
