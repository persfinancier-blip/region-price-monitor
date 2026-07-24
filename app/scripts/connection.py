"""`connection` script — the «Параметры подключения» tab's backend (ADR-0010, ADR-0014).

Thin shell over `app/io/*`: `load`/`save` round-trip `io.json` (atomic
temp+rename, mirroring `app/scripts/cities.py`); `columns` reads a source/sink
endpoint's header (csv first row / xlsx header row / db table columns) without
requiring a saved mapping; `validate_source`/`validate_sink` run the header
against a posted (possibly unsaved) mapping via `app/io/mapping.validate` +
`validate_known_fields`, collecting all violations in one message;
`preview_source` builds an unconfigured-in-`io.json` source via
`app/io/factory.build_product_source` and returns the first mapped rows. No
secret store (ADR-0009): a `database_url` is masked for display, and an empty
password on submit keeps the previously stored one (same pattern as proxies
in `app/scripts/cities.py`).
"""

import argparse
import csv
import json
import os
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import openpyxl

from app.config import Settings, get_settings
from app.io.base import (
    PRODUCT_FIELDS,
    REGION_FIELDS,
    REQUIRED_PRODUCT_FIELDS,
    REQUIRED_RESULT_FIELDS,
    RESULT_FIELDS,
    Mapping,
)
from app.io.factory import build_product_source
from app.io.mapping import (
    EndpointConfig,
    IoConfig,
    MappingError,
    load_io_config,
    validate,
    validate_known_fields,
)

_MASK = "***"


def _default_path(settings: Settings) -> str:
    return settings.io_config_path


def _endpoint_to_dict(endpoint: EndpointConfig | None) -> dict[str, Any] | None:
    if endpoint is None:
        return None
    raw: dict[str, Any] = {"kind": endpoint.kind, **endpoint.params}
    mapping: dict[str, Mapping] = {}
    if endpoint.products is not None:
        mapping["products"] = endpoint.products
    if endpoint.regions is not None:
        mapping["regions"] = endpoint.regions
    if endpoint.results is not None:
        mapping["results"] = endpoint.results
    if mapping:
        raw["mapping"] = mapping
    return raw


def load(settings: Settings | None = None) -> IoConfig:
    """Load `io.json`; a missing file yields an all-`None` config (local-first default)."""
    settings = settings or get_settings()
    return load_io_config(_default_path(settings))


def save(config: IoConfig, settings: Settings | None = None) -> None:
    """Persist `io.json` atomically (temp file + `os.replace`)."""
    settings = settings or get_settings()
    path = _default_path(settings)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    raw = {"source": _endpoint_to_dict(config.source), "sink": _endpoint_to_dict(config.sink)}
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def mask_database_url(database_url: str | None) -> str | None:
    """Return `None` unmasked, else the URL with its password replaced by `***`."""
    if database_url is None:
        return None
    parts = urlsplit(database_url)
    if parts.password is None:
        return database_url
    userinfo = parts.username or ""
    userinfo += f":{_MASK}"
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    netloc = f"{userinfo}@{host}" if userinfo else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def resolve_database_url(new_value: str | None, stored_value: str | None) -> str | None:
    """Empty `new_value` on submit keeps `stored_value` (same pattern as proxies, ADR-0009)."""
    return new_value if new_value else stored_value


def _csv_header(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        return next(reader, [])


def _xlsx_header(path: str, sheet: str | None, cell_range: str | None) -> list[str]:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    worksheet = workbook[sheet] if sheet else workbook.worksheets[0]
    cell_rows = list(worksheet[cell_range] if cell_range else worksheet.iter_rows())
    if not cell_rows:
        return []
    return [str(cell.value) if cell.value is not None else "" for cell in cell_rows[0]]


async def _db_header(database_url: str, table_name: str) -> list[str]:
    from sqlalchemy import MetaData, Table
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:

            def _reflect(sync_conn: Any) -> Table:
                return Table(table_name, MetaData(), autoload_with=sync_conn)

            table = await conn.run_sync(_reflect)
            return [col.name for col in table.columns]
    finally:
        await engine.dispose()


async def columns(endpoint: EndpointConfig, *, table: str | None = None) -> list[str]:
    """Return the available source/sink columns for an (unsaved) endpoint's header.

    `table` selects which table/file to read when an endpoint carries more than
    one (a source's `products`/`regions`); ignored for single-target endpoints.
    """
    if endpoint.kind == "csv":
        path = endpoint.params.get(f"{table}_path") if table else endpoint.params.get("path")
        if not path or not os.path.exists(path):
            return []
        return _csv_header(path)

    if endpoint.kind == "xlsx":
        if table:
            target = endpoint.params.get(table, {})
            path, sheet, cell_range = target.get("path"), target.get("sheet"), target.get("range")
        else:
            path, sheet, cell_range = (
                endpoint.params.get("path"),
                endpoint.params.get("sheet"),
                endpoint.params.get("range"),
            )
        if not path or not os.path.exists(path):
            return []
        return _xlsx_header(path, sheet, cell_range)

    if endpoint.kind == "db":
        database_url = endpoint.params.get("database_url")
        table_name = endpoint.params.get(f"{table}_table") if table else endpoint.params.get("results_table")
        if not database_url or not table_name:
            return []
        return await _db_header(database_url, table_name)

    return []


async def validate_source(endpoint: EndpointConfig) -> list[str]:
    """Validate a source endpoint's products/regions mapping against its actual header(s).

    Returns all violation messages (empty list = valid); never raises.
    """
    problems: list[str] = []

    products_mapping = endpoint.products or {}
    try:
        validate_known_fields(products_mapping, PRODUCT_FIELDS)
        header = await columns(endpoint, table="products")
        if header:
            validate(products_mapping, header, required=REQUIRED_PRODUCT_FIELDS)
    except MappingError as exc:
        problems.append(f"products: {exc}")

    regions_mapping = endpoint.regions or {}
    try:
        validate_known_fields(regions_mapping, REGION_FIELDS)
        header = await columns(endpoint, table="regions")
        if header:
            validate(regions_mapping, header, required=())
    except MappingError as exc:
        problems.append(f"regions: {exc}")

    return problems


async def validate_sink(endpoint: EndpointConfig) -> list[str]:
    """Validate a sink endpoint's results mapping against its actual header. Never raises."""
    problems: list[str] = []
    results_mapping = endpoint.results or {}
    try:
        validate_known_fields(results_mapping, RESULT_FIELDS)
        header = await columns(endpoint)
        if header:
            validate(results_mapping, header, required=REQUIRED_RESULT_FIELDS)
    except MappingError as exc:
        problems.append(f"results: {exc}")
    return problems


async def preview_source(endpoint: EndpointConfig, n: int = 5) -> dict[str, list[dict[str, Any]]]:
    """Build the (possibly unsaved) source and return the first `n` mapped products/regions rows."""
    source = build_product_source(endpoint)
    products = await source.read_products()
    regions = await source.read_regions()
    return {"products": products[:n], "regions": regions[:n]}


async def preview_sink_header(endpoint: EndpointConfig) -> list[str]:
    """Return the resolved output header (the mapping's target columns) for a sink endpoint."""
    return list((endpoint.results or {}).values())


def with_masked_database_url(endpoint: EndpointConfig | None) -> EndpointConfig | None:
    """Return a copy of `endpoint` with `database_url` masked, for safe display."""
    if endpoint is None or "database_url" not in endpoint.params:
        return endpoint
    params = dict(endpoint.params)
    params["database_url"] = mask_database_url(params["database_url"])
    return replace(endpoint, params=params)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `python -m app.scripts.connection {show,validate,preview}`."""
    parser = argparse.ArgumentParser(
        prog="app.scripts.connection", description="Inspect the configured source/sink (io.json)"
    )
    subparsers = parser.add_subparsers(dest="action")
    subparsers.add_parser("show", help="Print the current source/sink config (database_url masked)")
    subparsers.add_parser("validate", help="Validate the configured source and sink mappings")
    subparsers.add_parser("preview", help="Print the first mapped source rows")

    args = parser.parse_args(argv)
    settings = get_settings()
    config = load(settings)

    import asyncio

    if args.action == "validate":
        problems: list[str] = []
        if config.source is not None:
            problems += asyncio.run(validate_source(config.source))
        if config.sink is not None:
            problems += asyncio.run(validate_sink(config.sink))
        if problems:
            for problem in problems:
                print(problem)
            return 1
        print("ok")
        return 0

    if args.action == "preview":
        if config.source is None:
            print("no source configured")
            return 0
        result = asyncio.run(preview_source(config.source))
        for row in result["products"]:
            print(row)
        return 0

    print("source:", _endpoint_to_dict(with_masked_database_url(config.source)))
    print("sink:", _endpoint_to_dict(with_masked_database_url(config.sink)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
