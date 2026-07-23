"""Mapping config load + validate + preview (ADR-0010, SPEC-panel §5.2/§5.4).

The mapping table is declarative and data-driven: `{canonical_field: locator}`,
loaded from a local JSON config file (`settings.io_config_path`), split into a
`source` section (products/regions in) and a `sink` section (results out). It
is deliberately dumb about *what* a locator means — for csv/xlsx it is a
column header (or letter), for db it is a table column name; the adapter that
owns a given `kind` resolves it.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from app.io.base import Mapping


@dataclass(frozen=True)
class EndpointConfig:
    """One source or sink endpoint: its adapter `kind`, locator params, and field mapping."""

    kind: str
    params: dict[str, Any]
    products: Mapping | None = None
    regions: Mapping | None = None
    results: Mapping | None = None


@dataclass(frozen=True)
class IoConfig:
    """The full `io.json` shape: an optional `source` and an optional `sink`."""

    source: EndpointConfig | None
    sink: EndpointConfig | None


def _endpoint_from_dict(raw: dict[str, Any]) -> EndpointConfig:
    mapping = raw.get("mapping", {})
    return EndpointConfig(
        kind=raw["kind"],
        params={k: v for k, v in raw.items() if k not in ("kind", "mapping")},
        products=mapping.get("products"),
        regions=mapping.get("regions"),
        results=mapping.get("results"),
    )


def load_io_config(path: str) -> IoConfig:
    """Load `io.json`; a missing file yields an all-`None` config (local-first default)."""
    if not os.path.exists(path):
        return IoConfig(source=None, sink=None)

    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    source = _endpoint_from_dict(raw["source"]) if raw.get("source") else None
    sink = _endpoint_from_dict(raw["sink"]) if raw.get("sink") else None
    return IoConfig(source=source, sink=sink)


class MappingError(ValueError):
    """Raised when a mapping table references unknown, missing, or shifted columns."""


def validate(mapping: Mapping, header: list[str], *, required: tuple[str, ...]) -> None:
    """Validate a `{canonical_field: locator}` mapping against a source's actual header row.

    Flags, raising `MappingError` with all violations in one message:
    - missing required fields (in `required` but absent from `mapping`);
    - locators present in the mapping but absent from `header` (a shifted sheet, SPEC §5.2).

    Unknown canonical fields are flagged separately by `validate_known_fields`.
    """
    problems: list[str] = []

    missing_required = [field for field in required if field not in mapping]
    if missing_required:
        problems.append(f"missing required fields: {', '.join(missing_required)}")

    shifted = [f"{field} -> {locator}" for field, locator in mapping.items() if locator not in header]
    if shifted:
        problems.append(f"locators absent from source header: {', '.join(shifted)}")

    if problems:
        raise MappingError("; ".join(problems))


def validate_known_fields(mapping: Mapping, known_fields: tuple[str, ...]) -> None:
    """Raise `MappingError` if `mapping` references a canonical field outside `known_fields`."""
    unknown = [field for field in mapping if field not in known_fields]
    if unknown:
        raise MappingError(f"unknown canonical fields: {', '.join(unknown)}")


def apply_mapping(mapping: Mapping, row: dict[str, Any]) -> dict[str, Any]:
    """Map one source-native row (keyed by locator) to a canonical-keyed row."""
    return {field: row.get(locator) for field, locator in mapping.items()}


def reverse_apply_mapping(mapping: Mapping, row: dict[str, Any]) -> dict[str, Any]:
    """Map one canonical-keyed row to a sink-native row (keyed by locator)."""
    return {locator: row.get(field) for field, locator in mapping.items()}


def preview(rows: list[dict[str, Any]], mapping: Mapping, n: int = 5) -> list[dict[str, Any]]:
    """Return the first `n` source rows mapped to canonical field names, for a dry-run sanity check."""
    return [apply_mapping(mapping, row) for row in rows[:n]]


def resolve_column(locator: str, header: list[str]) -> int:
    """Resolve an xlsx locator (a header name, or an A1 column letter) to a 0-based index.

    Tried in order: exact header name match, then column-letter (`A`, `B`, ...,
    `AA`, ...) parsed as a 1-based spreadsheet column and converted to 0-based.
    """
    if locator in header:
        return header.index(locator)

    if locator.isalpha():
        index = 0
        for ch in locator.upper():
            index = index * 26 + (ord(ch) - ord("A") + 1)
        return index - 1

    raise MappingError(f"cannot resolve column locator: {locator!r}")


__all__ = [
    "EndpointConfig",
    "IoConfig",
    "MappingError",
    "apply_mapping",
    "load_io_config",
    "preview",
    "resolve_column",
    "reverse_apply_mapping",
    "validate",
    "validate_known_fields",
]
