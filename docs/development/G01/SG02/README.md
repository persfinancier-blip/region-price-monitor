# G01.SG02 planning index

Parent: Issue #32 — Proxy-First Regional Transport.
Status: **SEMANTIC_COMPILE_PASS (vertical only)**.

Durable artifacts:
- `vertical.md` — Process→Stage→Task contracts;
- `processes.md` — Process contracts;
- `compile-report.md` — virtual execution and reverse assembly;
- `issue-map.md` — GitHub identities;
- `prompts/work/G01-SG02/` — six initial Prompt candidates.

Hierarchy:
- PR01 Authenticated proxy context and safe transport contract
  - ST01/T01 Build authenticated ProxyContext
  - ST02/T01 Define typed transport outcomes and safe errors
- PR02 HTTP-stack proxy adapters
  - ST01/T01 requests adapter
  - ST02/T01 curl_cffi adapter
- PR03 Marketplace transport handoff and SG02 closure
  - ST01/T01 Bind WB/Ozon call paths to shared transport
  - ST02/T01 Prove SG02 proxy-first transport contract

Critical boundaries:
- no SG03 WB stock/optional-dest semantic implementation;
- no SG04 automatic Ozon regional/session bootstrap;
- no SG05 legacy fallback redesign;
- no SG06 matrix/persistence/scheduler work;
- supplied ProxyContext must never silently fall back to direct networking.
