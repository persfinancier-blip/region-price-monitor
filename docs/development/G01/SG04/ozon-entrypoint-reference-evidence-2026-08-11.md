# Ozon entrypoint reference evidence — 2026-08-11

## Owner-supplied files reviewed
Two files supplied from the recovered local `test_pars_2` lineage were reviewed directly:
- `ozon_parser.py` — server-side Ozon reader;
- `cookies_from_curl.py` — manual cookie extraction helper.

## What `ozon_parser.py` directly proves
The reader itself is browser-free and input-free at runtime. It performs one HTTP GET through `curl_cffi`:

`https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/product/<sku>/`

with:
- cookies loaded from a supplied JSON file;
- `curl_cffi` `impersonate="chrome"`;
- Ozon frontend headers including `x-o3-app-name`, `x-o3-app-version`, `x-o3-manifest-version`, request/page-view IDs and product referer;
- optional proxy argument;
- JSON response parsing from `widgetStates`.

The recovered lineage also exposed a historical semantic bug: selecting the first `webPrice`/`webSale` candidate could return a recommendation-card price for another SKU. That old output cannot be used as trustworthy regional-price evidence.

## Cookie/session evidence
Recovered cookie inspection indicates the historical `test_pars_2` cookies were anonymous/guest sessions. They do not establish that an authenticated account is required, and they did not reliably establish distinct per-city state. Therefore login is not part of the current primary hypothesis.

## Important transport caveat for G01
The reference parser's generic proxy helper must not be copied blindly into G01. G01 runtime evidence already proves the current ASocks gateway on port 443 requires an explicit HTTPS proxy scheme. G01 continues to use SG02 `ProxyContext` / transport adapters as the routing/auth authority.

## Version-header caveat
The recovered reference pins Ozon frontend build metadata (`x-o3-app-version` and `x-o3-manifest-version`) to a June 2026 frontend build. These are reference values, not proof they remain current. HTTP 400 is a typed signal to refresh them from a current request rather than guess.

## C08 live zero-human result
The owner executed the C08 headless-Playwright bootstrap twice on Windows, with workstation VPN enabled and disabled. Both runs produced the same Ozon-rendered incident page with title `Похоже, нет соединения`; the local browser-proxy bridge reported no internal error. The requested `entrypoint-api` request was never observed, so no curl_cffi replay occurred.

## C09 historical discriminator
C09 was prepared to compare headless and headed browser behavior through the same ProxyContext. It remains historical diagnostic work and is not the current acceptance path.

## C10 deferred regional comparison
C10 was prepared to compare two city ProxyContexts while reusing one identical anonymous cookie state. The owner stopped this as premature. C10 remains immutable historical contract and is **superseded for active execution** until one-proxy Ozon access is proven.

## C11 current one-proxy prerequisite
C11 is now the active cycle. Before any regional comparison, it uses exactly:
- one anonymous guest cookie/storage-state file;
- one SKU;
- one SG02 ProxyContext.

It performs:
1. neutral curl_cffi egress proof;
2. one real Ozon product-page request;
3. one direct `entrypoint-api` request for the same SKU.

No second proxy/city, regional comparison, Playwright, Selenium, login/password or PVZ selection is part of C11.

Primary acceptance is `OZON_SINGLE_PROXY_ENTRYPOINT_DATA_ACCESS_PROVEN`: entrypoint returns HTTP 200 decodable JSON and, when `pageInfo.url` exists, it binds to the requested SKU. Product-page loading is reported independently and cannot masquerade as entrypoint data success.

Only after C11 passes may C10 regional comparison resume.

No cookie values, proxy credentials or authorization headers are committed in this evidence note.
