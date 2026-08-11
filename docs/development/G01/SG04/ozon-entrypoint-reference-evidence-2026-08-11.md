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
- JSON response parsing from `widgetStates`, selecting keys containing `webPrice` or `webSale`.

The supplied reference parser extracts only `price` as a first-class value and sets `price_base` equal to that price. `cardPrice` and `originalPrice`, if present, remain only inside the returned raw widget object and are not normalized into dedicated fields by this reference implementation.

## What `cookies_from_curl.py` directly proves
The helper does not launch a browser from code. However, cookie provisioning remains a manual external step:
1. human opens Ozon in ordinary Chrome;
2. human selects the required city/pickup point and visits a product;
3. human copies an Ozon request as cURL (or copies the cookie string);
4. helper extracts cookie pairs and writes a per-city JSON file.

Therefore the steady-state reader is server-compatible and browser-free, but the supplied evidence does **not** prove autonomous zero-human regional cookie/session provisioning.

## Important transport caveat for G01
The reference parser's generic proxy helper must not be copied blindly into G01. G01 runtime evidence already proves the current ASocks gateway on port 443 requires an explicit HTTPS proxy scheme. G01 must continue to use SG02 `ProxyContext` / transport adapters as the proxy routing/auth authority.

## Version-header caveat
The supplied reference pins Ozon frontend build metadata (`x-o3-app-version` and `x-o3-manifest-version`) to a June 2026 frontend build. These values are evidence of the recovered reference request shape, not proof that they remain current. Any live failure attributed to them must be verified against a current owner-supplied Ozon request before repair.

## Claims NOT independently verified from the two supplied files
The following claims were described from the owner's/Claude's recovered local `test_pars_2` archive but are not independently evidenced by the two files supplied here:
- existence/size of the local `test_pars_2.zip` archive;
- exact `main.py` multi-region execution behavior;
- exact historical CSV files and timestamps;
- exact historical live values `209 / 188 / 1190` for SKU `1964684436`;
- age/expiry state of the archived cookie files.

Those claims require the recovered ZIP, `main.py`, CSV outputs, or corresponding artifacts before they can be accepted as durable runtime evidence.

## Architectural conclusion
This is a stronger reference for the Ozon **steady-state data reader** than the previously reviewed product-HTML reader: JSON endpoint + `curl_cffi` + anonymous guest cookies, no browser in routine reads.

Recovered cookie inspection indicates the historical `test_pars_2` cookies were guest/anonymous and did not reliably establish distinct regional state. Historical apparent regional price differences were also contaminated by the old first-`webPrice` bug. Therefore regional authority must not be assumed to live in those cookie files.

## C08 live zero-human result
The owner executed the C08 headless-Playwright bootstrap twice on Windows, first with workstation VPN enabled and then disabled. Both runs produced the same Ozon-rendered incident page with title `Похоже, нет соединения`; the local browser-proxy bridge reported no internal error. The requested `entrypoint-api` request was never observed, so no curl_cffi replay occurred.

The second run without workstation VPN means the workstation VPN alone does not explain the failure. C08 proved the browser reached Ozon content through the configured path, but Ozon refused to serve the normal application flow before entrypoint capture.

## C09 historical discriminator
C09 was prepared to compare headless and headed Playwright through the same ProxyContext. It is retained as historical diagnostic work but is not the current acceptance path.

## C10 deferred regional comparison
C10 was prepared to compare two city ProxyContexts while reusing one identical anonymous cookie state. The owner correctly stopped this as premature: no regional comparison should be attempted before one-proxy Ozon access itself is proven.

## C11 current one-proxy gate
C11 is now the active prerequisite. It uses exactly one ProxyContext, one anonymous guest cookie/storage-state file and one SKU. It performs:
1. neutral curl_cffi egress proof;
2. one real Ozon product-page request;
3. one direct `entrypoint-api` request for the same SKU.

No second proxy/city, regional comparison, Playwright, Selenium, login/password or PVZ selection is part of C11.

Primary acceptance is `OZON_SINGLE_PROXY_ENTRYPOINT_DATA_ACCESS_PROVEN`: HTTP 200 + decodable JSON from entrypoint, bound to the requested SKU when `pageInfo.url` is present. Product-page HTTP reachability alone is reported separately and cannot masquerade as entrypoint data success.

Only after C11 passes may regional proxy effect work resume.

No cookie values, proxy credentials or authorization headers are committed in this evidence note.
