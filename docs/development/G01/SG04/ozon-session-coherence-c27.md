# Ozon session coherence C27

C27 isolates one hypothesis from the latest live evidence: a browser bootstrap can yield an API-usable Ozon session even when the browser UI itself shows a challenge.

The checkpoint does not interact with or submit the challenge. It verifies session coherence across the browser bootstrap and the subsequent lightweight HTTP client.

## Coherence requirements

- one fresh mobile `hold-session-session-<id>` identity;
- selected proxy IP == Camoufox browser IP == curl_cffi IP;
- complete browser cookie jar copied without flattening domain/path scoped duplicates;
- exact browser User-Agent reused by the HTTP client;
- browser family and curl_cffi impersonation family must match;
- for Camoufox/Firefox, curl_cffi uses only the Firefox impersonation family;
- browser and curl_cffi both query the same neutral TLS fingerprint endpoint through the same sticky proxy;
- `ja3_hash`, `ja4`, and `akamai_hash` are compared where present;
- any compared TLS/HTTP2 fingerprint mismatch stops the run before the Ozon price request;
- cookie values and proxy credentials remain memory-only.

## Why this differs from the previous standalone probe

The earlier standalone probe flattened cookies into a `dict[name] = value` and then rotated Chrome TLS impersonation profiles even though Camoufox reported a Firefox User-Agent. C27 removes both inconsistencies and verifies the resulting browser/HTTP fingerprints rather than assuming they match.

## Live acceptance

`OZON_SESSION_COHERENCE_PRICE_PROVEN` means one run proved:

`selected sticky IP == browser IP == curl IP`

plus matching neutral TLS/HTTP2 fingerprints for the compared fields, followed by an exact requested-SKU price parsed through the existing strict Ozon price parser.
