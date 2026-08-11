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
This is a stronger reference for the Ozon **steady-state data reader** than the previously reviewed product-HTML reader: JSON endpoint + `curl_cffi` + regional cookies, no browser in routine reads.

It still does not, by itself, satisfy SG04's autonomous primary acceptance because regional cookies are manually provisioned outside the server runtime. It should be tested as the exact owner-supplied Ozon data endpoint once fresh cookie/session evidence is available or the owner explicitly changes the provisioning contract.

## C08 live zero-human result
The owner executed the C08 headless-Playwright bootstrap twice on Windows, first with the workstation VPN enabled and then disabled. Both runs produced the same Ozon-rendered incident page with title `Похоже, нет соединения`; the page advised disabling VPN and included an incident identifier. The local browser-proxy bridge reported no internal error. A small cookie state was created, but the requested `entrypoint-api` request was never observed, so no curl_cffi replay occurred.

The second run without workstation VPN means the workstation VPN alone does not explain the failure. C08 proved the browser reached Ozon content through the configured path, but Ozon refused to serve the normal application flow before entrypoint capture.

The original generic `OZON_ZERO_HUMAN_ENTRYPOINT_NOT_OBSERVED` classification was too weak. The historical C08 probe has been repaired so this exact page is typed as `OZON_ZERO_HUMAN_BROWSER_NETWORK_DENIED` on future reruns.

## C09 discriminator
Before adding login/session complexity, discriminate route/IP denial from headless-specific denial.

C09 compares `curl_cffi`, Playwright headless and Playwright headed using the same SG02 ProxyContext and requires matching neutral egress identity. Both browser modes then visit the same Ozon SKU with zero user interaction.

Typed evidence includes:
- `OZON_HEADLESS_SPECIFIC_DENIAL_EVIDENCED` — headless is denied while headed gets farther / observes entrypoint;
- `OZON_ROUTE_DENIED_BOTH_BROWSER_MODES` — both modes receive the Ozon network/VPN denial on the same proven egress;
- `OZON_BROWSER_PROXY_BINDING_UNPROVEN` — neutral egress identities do not match;
- explicit entrypoint-observed gates for either mode.

Headed success is diagnostic only. Linux production acceptance would still require a zero-human Linux/Xvfb or equivalent proof.

No cookie values, proxy credentials or authorization headers are committed in this evidence note.
