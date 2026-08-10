# G01.SG02 C02 repair — browser proxy authority compatibility

## Trigger
Whole-G01 reverse compilation after SG06 found a cross-SG contradiction: SG02 C01 Task #54 / compile wording required every Ozon network call to use the `curl_cffi` adapter, while active SG04 C02 correctly allows hidden/headless Selenium/Chrome as an autonomous primary engine.

## Finding
The architectural invariant is **one city-bound ProxyContext authority**, not one network library.

Correct composition:

`CityRecord -> SG02 ProxyContext -> requests adapter (WB)`

`CityRecord -> SG02 ProxyContext -> curl_cffi adapter (Ozon HTTP)`

`CityRecord -> SG02 ProxyContext -> SG04-owned browser proxy adaptation (Ozon hidden browser)`

The browser adapter/projection may be SG04-specific because browser startup, authentication mechanics, navigation, context verification and lifecycle are SG04 marketplace semantics. It may not independently read/invent a second proxy host/user/password authority or silently go direct.

## Active Prompt repair
Only Tasks #54/#55 required new Prompt cycles:
- `PR03-ST01-T01-C02.I01.md`
- `PR03-ST02-T01-C02.I01.md`

Their C01 Prompts remain superseded immutable history.

PR01 ProxyContext and PR02 requests/curl_cffi adapter Tasks remain valid and unchanged.

## Recompile result
`SEMANTIC_COMPILE_PASS (SG02 repaired C02 boundary)`.

The repair preserves:
- minimum SG01 CityRecord;
- SG02 sole proxy authority;
- existing HTTP adapters;
- no silent direct fallback;
- SG04 ownership of hidden-browser semantics;
- no SG05 coupling.

This repair is required for whole-G01 compilation and supersedes any older SG02 wording that requires hidden-browser traffic itself to transit through `curl_cffi`.