# Ozon hidden/direct access — GitHub research 2026-08-11

## Question
Can the production Linux server obtain Ozon data as `SKU + city -> HTTP/API -> result` with **no browser installed/running on our server**?

This research is separate from C16/C17 live evidence.

## Existing Ozon HTTP lineage
Public historical Ozon parsers call the internal JSON page API (`composer-api` / later `entrypoint-api`) and parse `widgetStates`. The recovered owner reference uses:

`GET https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/product/<sku>/`

with dweb `x-o3-*` headers, browser TLS impersonation, proxy and session cookies. C17 now tests the strongest simpler hypothesis first: selected sticky RU mobile proxy + direct endpoint + zero cookies.

## GitHub candidates

### 1. Bright Data Web Unlocker — exact managed-unlocker architecture
Repository: `luminati-io/web-unlocker-api`.

The repository documents a direct API call to Bright Data where the caller supplies the target URL and receives raw target content. The service handles proxy management, CAPTCHA, JavaScript rendering, retries and geo/mobile targeting.

Architecture fit:
`our Linux -> HTTPS API -> Bright Data infrastructure -> Ozon -> raw response`.

Browser on our server: **NO**.
Self-hosted unlocking engine: **NO**. The GitHub repository is integration/example code; the anti-bot infrastructure is the managed Bright Data service.

### 2. Oxylabs Web Scraper API / Web Unblocker
Repository: `oxylabs/web-scraper-api`.

Documents an all-in-one remote scraping API with proxies, CAPTCHA handling, JS rendering and raw/structured output. Their Web Unblocker is proxy-style access; their Scraper API is request/result style.

Browser on our server: **NO** when using their managed API.
Self-hosted unlocking engine: **NO**.

### 3. Scrapeless Web Unlocker
Repository: `scrapeless-ai/scrapeless-sdk-python`.

Python SDK exposes a `webunlocker` actor: URL + proxy country + method -> remote result. Provider handles proxies/browser/captcha infrastructure.

Browser on our server: **NO**.
Self-hosted unlocking engine: **NO**.

### 4. Browserless
Repository: `browserless/browserless`.

Provides a remote REST/WebSocket browser service. Cloud can expose stealth/captcha/proxy features. The open-source self-hosted form launches Chromium internally.

Browser on our server if self-hosted: **YES**.
Therefore it is not the requested browser-free production architecture, though its managed cloud could be used remotely.

### 5. FlareSolverr
Repository: `FlareSolverr/FlareSolverr`.

Looks like a simple local HTTP API but internally creates Chrome through Selenium/undetected-chromedriver and returns HTML/cookies after the challenge.

Browser on our server if self-hosted: **YES**.
Not a browser-free solution.

### 6. Scrapling
Repository: `D4Vinci/Scrapling`.

Has a fast HTTP Fetcher with TLS/browser impersonation and proxy rotation. Its stronger anti-bot fetchers install browser dependencies. Good library, but not a magic self-hosted browserless CAPTCHA/unlocker service.

### 7. tls-client
Repository: `bogdanfinn/tls-client`.

Pure HTTP client with browser TLS/HTTP1.1/HTTP2/HTTP3 fingerprints, header ordering, proxies and cookie jar. This is a legitimate browser-free alternative transport to benchmark against `curl_cffi` if fingerprint fidelity is the blocker.

It does **not** itself solve target-specific JavaScript challenges/CAPTCHAs or manufacture Ozon application session state.

### 8. curl_cffi current line
Repository: `lexiforest/curl_cffi`.

Current releases support Chrome 145/146, HTTP/3 fingerprints, proxy support, cookie behavior and explicit header ordering improvements. The project is a browser-fingerprint HTTP transport, not a managed challenge-solving service.

## Key distinction
There are two fundamentally different categories:

1. **Pure HTTP impersonation** (`curl_cffi`, `tls-client`): no browser anywhere, very cheap/fast, but works only if Ozon accepts the request/session/fingerprint.
2. **Managed Unlocker API** (Bright Data, Oxylabs, Scrapeless): our server has no browser, but the provider may use browser/challenge infrastructure remotely. This is exactly the requested topology, but it is a paid external service rather than a free self-hosted magic bypass.

Open-source projects that offer a local 'unlocker API' (FlareSolverr, Browserless self-hosted, stealth fetchers) generally hide a browser **inside the service**; they do not satisfy the requirement that the production server contain no browser runtime.

## Decision tree for G01

### C16 first
Reproduce recovered Claude mobile-proxy selector exactly:
`rotate hold-session-session-<id> -> curl_cffi IP/ISP -> stop on MTS/Beeline/MegaFon/T2/Yota`.

### C17 second
With the exact selected sticky session:
`direct entrypoint-api + zero cookies + no home + no product HTML + no browser`.

If C17 PASS: use direct Ozon endpoint; no unlocker and no browser required.

If C17 returns challenge/403: the direct endpoint requires more than just a good mobile route. At that point there are only two bounded next experiments:
- benchmark a second pure-HTTP fingerprint stack (`tls-client` / latest curl_cffi profile fidelity), or
- test one managed unlocker provider with the Ozon entrypoint URL and our required geo contract.

Do not return to product HTML/home warmup/ordinary Playwright loops.

## Production target if managed unlocker is required

`CityRecord -> provider geo/sticky context -> ManagedUnlocker.request(Ozon entrypoint URL, headers) -> Ozon JSON -> strict layout/stateId parser -> RunResult`

The provider adapter must be replaceable; Ozon parsing semantics remain provider-independent.
