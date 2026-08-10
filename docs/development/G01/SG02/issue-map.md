# SG02 durable identity map

Parent Subgoal: Issue #32

Proposed hierarchy:
- `G01.SG02.PR01` Authenticated proxy context and safe transport contract
  - `G01.SG02.PR01.ST01.T01` Build authenticated ProxyContext from minimum CityRecord
  - `G01.SG02.PR01.ST02.T01` Define typed transport outcomes and safe errors
- `G01.SG02.PR02` HTTP-stack proxy adapters
  - `G01.SG02.PR02.ST01.T01` Route requests traffic through ProxyContext
  - `G01.SG02.PR02.ST02.T01` Route curl_cffi traffic through ProxyContext
- `G01.SG02.PR03` Marketplace transport handoff and SG02 closure
  - `G01.SG02.PR03.ST01.T01` Bind WB and Ozon request paths to shared transport
  - `G01.SG02.PR03.ST02.T01` Prove proxy-first transport contract

Exact GitHub Issue numbers are materialized after semantic compilation and then filled into this map.
