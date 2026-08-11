# G01 SG02 runtime proxy-scheme finding

## Observed failure

The first Wave 2 live probe accepted `host:port` and therefore used ProxyContext's legacy HTTP default. The operator's ASocks endpoint was configured as an **HTTPS proxy** on port 443. Native curl evidence on the wrong scheme showed plaintext HTTP CONNECT sent to the proxy and nginx HTTP 400 before marketplace semantics.

## Proven provider path

Operator Windows native curl using explicit `https://<proxy-host>:443` plus proxy Basic auth established TLS to the proxy, then received `HTTP/1.1 200 Connection Established` for `https://i.pn`. The neutral endpoint reported Russia / Novosibirsk Oblast / Novosibirsk and `mobile=true`.

Credentials are intentionally not stored in this repository.

## Repair

- Live/production probe requires explicit `scheme://host:port` and fails closed when the scheme is omitted.
- Legacy non-live construction still supports `host:port -> http` for backward compatibility.
- Explicit HTTPS scheme is preserved through Requests, curl_cffi and browser projection.
- curl_cffi receives proxy URL and proxy Basic auth separately.
- Neutral proof uses the provider reference target `https://i.pn`.
- Marketplace probes are blocked until native curl, Requests and curl_cffi all pass and all three neutral responses confirm the requested city.

## Ozon provider note

Historical ASocks support guidance supplied by the operator suggested mobile+residential, country-only and hold-session when Ozon rejects IP reputation before anti-bot handling. This is retained only as a diagnostic/fallback lead. It does not satisfy or replace the G01 city-bound context contract unless requested-city semantics are independently proven.
