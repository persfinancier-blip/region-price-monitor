# Ozon proven cookie-reader evidence — 2026-08-11

## Source material supplied by owner
A self-contained `ozon_price_fetch` package was supplied for review. It contains:
- `warm_cookies.py` — visible Playwright browser warm-up;
- `ozon_price.py` — steady-state `curl_cffi` price reader;
- example/README/requirements.

## Proven working contour represented by the package
1. Open a **visible** browser.
2. Human solves captcha when presented.
3. Human selects a pickup point/region.
4. Browser visits the product page and exports cookies.
5. Later price reads run without a browser via `curl_cffi` with Chrome TLS impersonation and the warmed cookies.
6. If cookies were warmed through a proxy, reads must use the same IP/proxy.
7. Region is represented by the warmed session/cookies (one profile per city), not proven to be supplied by proxy IP alone.
8. Price is parsed from Ozon `webPrice` / `webSale` widget state, with bounded fallback to Product JSON-LD; broad page-wide ruble-number search is intentionally rejected.

## Architectural conclusion
This package is valid **historical/legacy working evidence for price reading**, but it does **not** satisfy G01.SG04 primary acceptance because normal preparation requires visible browser + human captcha/PVZ selection + per-city warmed profiles/cookies.

Therefore:
- preserve it as a proven reference/fallback implementation;
- do not claim it proves autonomous proxy-first Ozon regional collection;
- do not silently redefine SG04 primary to require its manual warm-up;
- SG04 primary remains runtime-blocked until a zero-human session/region mechanism is evidenced, or the project contract is explicitly changed by the owner;
- mobile proxy is compatible as an underlying transport for this reader only when the same IP is used for warm and read; it is not proven to replace the cookie/session regional state.

## Security
No cookie values or proxy credentials from the supplied material are committed here.
