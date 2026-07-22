# prompt-00 — Feasibility spike (go/no-go gate)

- **Branch:** `spike/feasibility`
- **Commit type:** `chore:` (throwaway spike — code is NOT the deliverable, the report is)
- **Docs:** [docs/TZ.md](../docs/TZ.md), [ADR-0002](../docs/adr/0002-scraping-strategy.md), [ADR-0003](../docs/adr/0003-proxy-provider.md)

## Goal

De-risk the project BEFORE real development. Prove the mechanisms that can kill it, and nothing else. This is a **throwaway** — no DB, no scheduler, no clean architecture. One script, a printed report, a go/no-go verdict.

## Prerequisites

- **Regional proxy** trial — at least **2 RF regions** far apart (e.g. Moscow + a Far-East/remote region), residential or mobile. **Owner to provide creds** (see below).
- **Sample SKUs (provided):**
  - WB `nmId` **629760017** — `https://www.wildberries.ru/catalog/629760017/detail.aspx`
  - Ozon product **3129447770** — `https://www.ozon.ru/product/3129447770/`
- **Price fields to capture (required):** base price, discounted price, **WB wallet** price (WB), **Ozon card** price (Ozon).

## What to prove (each = explicit PASS/FAIL in the report)

1. **Geo-preset access works.** Playwright (Chromium, stealth) can open a marketplace product page **through a region-specific proxy** with the site's geo set (WB `dest`, Ozon city/coords), and the page loads as a real client would see it from that region.
2. **Region changes the observed price.** For the SAME SKU, two different regions yield a captured result that reflects the region (different price and/or different delivery/availability). Even "same price, different delivery" counts as proof the geo path works — record the raw numbers.
3. **Specific-SKU price is readable.** For each sample SKU on **WB** and **Ozon**, extract the current price (+ the fields the owner named) reliably — via captured XHR/fetch response or DOM.
4. **Antibot passability.** Repeat each capture several times across the regions/proxies without getting hard-blocked; if a captcha/block appears (expected on Ozon), confirm the detect-and-retry-via-another-proxy path recovers it. Record block rate.

## Body (concrete steps)

1. Minimal `spike/` script (Playwright async). Config (proxy creds, sample SKUs) via env / a local `spike.env` — **never committed**.
2. WB path: open product through Region-A proxy + `dest`, capture price; repeat for Region-B; repeat both a few times. Log raw captured JSON/price per (SKU × region × attempt).
3. Ozon path: same, with stronger stealth; explicitly detect captcha/block and retry through another proxy lease.
4. Produce **`docs/spike-report.md`** (Russian, for the owner): a table SKU × region × price + PASS/FAIL per mechanism (1–4) + observed block rate + a clear **GO / NO-GO** verdict with any caveats (e.g. "Ozon needs antidetect build X").

## Explicitly NOT in scope

DB writes, schema, scheduler, queue, retries framework, clean interfaces, tests-as-gate. Those come only if the verdict is GO. Do not build the wrapping — it is decoration for this step.

## Constraints

- Secrets (proxy creds, SKUs) never committed; use `spike.env` gitignored.
- Only public price data; polite pacing; do not place orders.
- Owner-facing report in Russian; code/comments in English.

## Definition of Done

- `docs/spike-report.md` exists with: SKU × region × price table, PASS/FAIL for mechanisms 1–4, block rate, and a GO / NO-GO verdict.
- The spike is reproducible from the script + `spike.env.example`.
- `docs/DEVLOG.md` updated with the spike outcome.
- **No production code merged from this spike** — its only output is the report and the verdict. On GO, real work starts at `prompt-01-skeleton`.
