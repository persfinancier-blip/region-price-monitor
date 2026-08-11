# SG02 provider note

The user-facing city contract remains provider-agnostic and minimal:
`city`, `proxy`, `proxy_user`, `proxy_password`, optional `wb_dest`.

`proxy` is the connection address field. It may contain `host:port` or an explicit supported proxy URI if needed by the actual provider/runtime. Provider management IDs/API keys/rotation controls are not required by G01 and must not become mandatory CityRecord fields without new evidence.

Protocol/provider-specific live compatibility is an integration fixture, not a reason to add another city column during planning.
