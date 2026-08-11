# Owner-captured current Wildberries endpoint evidence — 2026-08-11

Source: owner-provided browser DevTools `Copy as cURL` captures for control SKU `629760017`.

## Security handling
The original capture contained live cookie/session/token values and device identifiers. Those values are intentionally NOT stored in Git. Only endpoint shapes, query parameter names, header names and cookie names are retained. Any exposed session values should be treated as compromised/test-only and rotated when practical.

## Current observed request shapes

### 1. Internal u-card detail — single SKU
`https://www.wildberries.ru/__internal/u-card/cards/v4/detail`

Observed query:
- `appType=1`
- `curr=rub`
- `dest=-365341`
- `spp=30`
- `hide_vflags=4294967296`
- `hide_dtype=15`
- `mtype=257`
- `lang=ru`
- `ab_testing=false`
- `nm=629760017`

Observed request header names include:
- `accept`
- `accept-language`
- `cookie`
- `deviceid`
- `priority`
- `referer`
- `sec-ch-ua`
- `sec-ch-ua-mobile`
- `sec-ch-ua-platform`
- `sec-fetch-dest`
- `sec-fetch-mode`
- `sec-fetch-site`
- `user-agent`
- `x-requested-with`
- `x-spa-version`

Observed cookie names include `_wbauid`, `wbx-validation-key`, `external-locale`, `feedbacks_link_accepted`, `_cp`, `x-supplier-id-external`, `__zzatw-wb`, `cfidsw-wb`, `x_wbaas_token`. Values are deliberately omitted.

### 2. Internal u-card detail — multi-SKU
Same endpoint and parameter/header shape as above, with `nm` containing a semicolon-separated SKU list including `629760017`.

### 3. Product static card JSON
`https://mow-basket-cdn-19.geobasket.ru/vol6297/part629760/629760017/info/ru/card.json`

Observed header names include `referer`, `user-agent`, `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform`.

### 4. Supplier shipment request
`https://suppliers-shipment-2.wildberries.ru/api/v1/suppliers/17470`

Observed query: `curr=RUB`.
Observed header names include `accept`, `accept-language`, `origin`, `priority`, `referer`, `sec-ch-*`, `sec-fetch-*`, `user-agent`, `x-client-name`.

### 5. Card variants metadata
`https://www.wildberries.ru/__internal/meta/meta/ru/common/v5/search/cardVariants`

Observed query:
- `nmid=629760017`
- `imtid=1493522920`
- `dest=-365341`

Observed header/cookie family is similar to the internal u-card request.

### 6. Duplicates/search metadata
`https://www.wildberries.ru/__internal/meta/duplicates/ru/common/v8/search`

Observed query includes:
- `appType=1`
- `curr=rub`
- `dest=-365341`
- `spp=30`
- `hide_vflags=4294967296`
- `hide_dtype=15`
- `ab_ranking=price_rating`
- `ab_photo_search_wo_filters=1`
- `lang=ru`
- `locale=ru`
- `match_id=493099`
- `anchor_id=629760017`
- `anchor_supplier_id=17470`
- `sort=popular`
- `page=1`

Additional observed header: `type: product_card`; `x-clientinfo` contains the app/currency/spp/dest/lang/locale context.

## Important delta from historical parser
Historical G01/July parser used:
`https://card.wb.ru/cards/v4/detail`

Current owner capture uses:
`https://www.wildberries.ru/__internal/u-card/cards/v4/detail`

These are distinct hosts/paths. The current capture is therefore a concrete candidate for the later data-access cycle and explains why replaying the historical `card.wb.ru` request may no longer represent current frontend behavior.

## Current gate boundary
Do NOT call these data endpoints as part of C07 server visibility. C07 proves only server-side reachability of the official WB/Ozon product pages through ProxyContext. After `SERVER_SEES_WB_AND_OZON`, the first WB data replay should use the owner-captured `__internal/u-card/cards/v4/detail` shape with the smallest necessary current header/session context, then determine which cookie/header fields are actually required. Stock remains a separate semantic proof.
