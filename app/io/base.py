"""I/O seam (ADR-0010) — source/sink Protocols mirroring the `app/storage/` seam style.

Both directions move data through one canonical dictionary (SPEC-panel §7), so
adapters never see each other's native shapes: a `ProductSource` yields rows
already keyed by canonical field names (mapping applied inside the adapter), a
`ResultSink` consumes canonical-keyed rows and writes them out mapped to the
target's own columns. `app/io/factory.py` picks a concrete adapter by
`kind` (`json` | `csv` | `xlsx` | `db`).
"""

from typing import Any, Protocol

# Reference subset — product/region list input (SPEC-panel §7).
PRODUCT_FIELDS = ("marketplace", "sku", "url", "name")
REGION_FIELDS = ("region", "name", "geo")

# Full set — measurement result output (SPEC-panel §7). The price-field list
# (price / price_no_card / price_card) is explicitly open (SPEC-panel §9.5);
# keep this tuple as the single source of truth so it can grow without
# touching adapter code.
RESULT_FIELDS = (
    "marketplace",
    "sku",
    "url",
    "name",
    "region",
    "price",
    "price_no_card",
    "price_card",
    "currency",
    "availability",
    "measured_at",
    "status",
)

REQUIRED_PRODUCT_FIELDS = ("marketplace", "sku", "url", "name")
REQUIRED_RESULT_FIELDS = ("sku", "region", "price", "measured_at", "status")

# A locator for one canonical field within a source/sink: a column header or
# letter (csv/xlsx) or a table column name (db). The concrete shape is
# adapter-specific; the mapping table only pairs a canonical field with it.
SourceLocator = str
Mapping = dict[str, SourceLocator]


class ProductSource(Protocol):
    """Read the product/region reference lists as canonical-keyed rows."""

    async def read_products(self) -> list[dict[str, Any]]: ...

    async def read_regions(self) -> list[dict[str, Any]]: ...


class ResultSink(Protocol):
    """Write measurement result rows (canonical-keyed) to the configured target."""

    async def write_snapshots(self, rows: list[dict[str, Any]]) -> int: ...
