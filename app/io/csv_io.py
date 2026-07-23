"""CSV source/sink (ADR-0010, SPEC-panel §5.1/§5.3) — `canonical -> column header` mapping."""

import csv
import os
from typing import Any

from app.io.base import REQUIRED_PRODUCT_FIELDS, Mapping
from app.io.mapping import apply_mapping, reverse_apply_mapping, validate


def _read_rows(path: str) -> tuple[list[str], list[dict[str, Any]]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return header, rows


class CsvProductSource:
    """Reads a products CSV and a regions CSV through their `canonical -> column` mappings."""

    def __init__(
        self,
        products_path: str | None,
        regions_path: str | None,
        products_mapping: Mapping | None,
        regions_mapping: Mapping | None,
    ) -> None:
        self._products_path = products_path
        self._regions_path = regions_path
        self._products_mapping = products_mapping or {}
        self._regions_mapping = regions_mapping or {}

    async def read_products(self) -> list[dict[str, Any]]:
        if not self._products_path:
            return []
        header, rows = _read_rows(self._products_path)
        validate(self._products_mapping, header, required=REQUIRED_PRODUCT_FIELDS)
        return [apply_mapping(self._products_mapping, row) for row in rows]

    async def read_regions(self) -> list[dict[str, Any]]:
        if not self._regions_path:
            return []
        header, rows = _read_rows(self._regions_path)
        validate(self._regions_mapping, header, required=())
        return [apply_mapping(self._regions_mapping, row) for row in rows]


class CsvResultSink:
    """Writes canonical result rows to a CSV file through the `canonical -> column` mapping."""

    def __init__(self, path: str, mapping: Mapping) -> None:
        self._path = path
        self._mapping = mapping

    async def write_snapshots(self, rows: list[dict[str, Any]]) -> int:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        fieldnames = list(self._mapping.values())
        with open(self._path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                mapped = reverse_apply_mapping(self._mapping, row)
                writer.writerow({k: ("" if v is None else str(v)) for k, v in mapped.items()})
        return len(rows)
