# G01.SG02 Process contracts

Parent: Issue #32. Canonical proposed vertical: `docs/development/G01/SG02/vertical.md`.

## PR01 — Authenticated proxy context and safe transport contract
Input: SG01 CityRecord.
Output: safe `ProxyContext` + typed source-neutral transport outcome/error contract.
Children:
- ST01/T01 ProxyContext construction;
- ST02/T01 structured outcome/redaction.
Acceptance: minimum city fields suffice; authentication applied; malformed values explicit; credentials never enter safe/public diagnostics; no marketplace parsing or browser/profile dependency.

## PR02 — HTTP-stack proxy adapters
Input: PR01 context/contracts + request specification.
Output: `requests` and `curl_cffi` adapters consuming identical ProxyContext semantics.
Children:
- ST01/T01 requests adapter;
- ST02/T01 curl_cffi adapter.
Acceptance: both stacks apply authenticated proxy to all calls; no silent direct fallback; safe typed errors; no legacy profile requirement.

## PR03 — Marketplace transport handoff and SG02 closure
Input: PR01/PR02 outputs + existing WB/Ozon network call boundaries.
Output: both collectors bound to the shared transport + deterministic SG02 evidence.
Children:
- ST01/T01 collector binding;
- ST02/T01 acceptance/compile gate.
Acceptance: shared proxy context demonstrably reaches both marketplace call paths; failures remain explicit; credentials remain secret; transport itself needs no manual warming, cookies/profile path or WB dest.

## Composition rule
`PR01 + PR02 + PR03 = SG02` only if all SG02 Issue #32 acceptance clauses have direct evidence and no child absorbs SG03/SG04/SG05/SG06 responsibility.
