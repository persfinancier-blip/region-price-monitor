"""Default JSON source/sink (ADR-0010) — canonical-keyed passthrough, today's shape unchanged.

JSON needs no mapping: product files are already `{marketplace, sku, url, name}`
and region files are already `{code, name, geo}`, which is exactly what
`app/scripts/control_panel.py`'s `import-products`/`import-regions` have always
read. This adapter exists so `make_product_source`/`make_result_sink` have a
`kind: json` implementation with the same shape as every other adapter,
without changing the on-disk format or CLI behaviour.
"""

import json
from typing import Any


class JsonProductSource:
    """Reads a products JSON file and a regions JSON file, no mapping needed."""

    def __init__(self, products_path: str | None, regions_path: str | None) -> None:
        self._products_path = products_path
        self._regions_path = regions_path

    async def read_products(self) -> list[dict[str, Any]]:
        if not self._products_path:
            return []
        with open(self._products_path, encoding="utf-8") as fh:
            items: list[dict[str, Any]] = json.load(fh)
        return items

    async def read_regions(self) -> list[dict[str, Any]]:
        if not self._regions_path:
            return []
        with open(self._regions_path, encoding="utf-8") as fh:
            items: list[dict[str, Any]] = json.load(fh)
        return items


class JsonResultSink:
    """Writes canonical result rows to a JSON file (whole-array, overwritten)."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def write_snapshots(self, rows: list[dict[str, Any]]) -> int:
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2, default=str)
        return len(rows)
