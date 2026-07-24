"""app.scripts.connection — io.json load/save round-trip, validate, preview, masking (ADR-0014)."""

import csv
import json

import openpyxl

from app.config import Settings
from app.io.factory import build_product_source, build_result_sink, make_product_source, make_result_sink
from app.io.mapping import EndpointConfig, IoConfig
from app.scripts import connection


def test_load_save_round_trip_is_atomic(tmp_path) -> None:
    io_path = tmp_path / "io.json"
    settings = Settings(io_config_path=str(io_path))
    config = IoConfig(
        source=EndpointConfig(
            kind="csv",
            params={"products_path": "products.csv"},
            products={"sku": "SKU"},
        ),
        sink=None,
    )

    connection.save(config, settings)
    assert not (tmp_path / "io.json.tmp").exists()

    loaded = connection.load(settings)

    assert loaded.source is not None
    assert loaded.source.kind == "csv"
    assert loaded.source.params == {"products_path": "products.csv"}
    assert loaded.source.products == {"sku": "SKU"}
    assert loaded.sink is None


def test_load_missing_file_returns_empty_config(tmp_path) -> None:
    settings = Settings(io_config_path=str(tmp_path / "missing.json"))

    config = connection.load(settings)

    assert config.source is None
    assert config.sink is None


async def test_validate_source_catches_missing_required(tmp_path) -> None:
    path = tmp_path / "products.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Артикул", "Название"])
        writer.writerow(["1", "A"])

    endpoint = EndpointConfig(
        kind="csv",
        params={"products_path": str(path)},
        products={"sku": "Артикул", "name": "Название"},
    )

    errors = await connection.validate_source(endpoint)

    assert errors
    assert any("missing required fields" in e for e in errors)


async def test_validate_source_catches_shifted_column(tmp_path) -> None:
    path = tmp_path / "products.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["marketplace", "sku", "url", "name"])
        writer.writerow(["wb", "1", "https://x", "A"])

    endpoint = EndpointConfig(
        kind="csv",
        params={"products_path": str(path)},
        products={
            "marketplace": "marketplace",
            "sku": "sku",
            "url": "url",
            "name": "shifted_column",
        },
    )

    errors = await connection.validate_source(endpoint)

    assert errors
    assert any("absent from source header" in e for e in errors)


async def test_preview_source_maps_csv_rows(tmp_path) -> None:
    path = tmp_path / "products.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Площадка", "Артикул", "Ссылка", "Название"])
        writer.writerow(["wb", "1", "https://x/1", "Товар А"])

    endpoint = EndpointConfig(
        kind="csv",
        params={"products_path": str(path)},
        products={"marketplace": "Площадка", "sku": "Артикул", "url": "Ссылка", "name": "Название"},
    )

    result = await connection.preview_source(endpoint)

    assert result["products"] == [{"marketplace": "wb", "sku": "1", "url": "https://x/1", "name": "Товар А"}]
    assert result["regions"] == []


async def test_preview_source_maps_xlsx_rows(tmp_path) -> None:
    path = tmp_path / "products.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Площадка", "Артикул", "Ссылка", "Название"])
    sheet.append(["ozon", "2", "https://x/2", "Товар Б"])
    workbook.save(path)

    endpoint = EndpointConfig(
        kind="xlsx",
        params={"products": {"path": str(path)}, "regions": {}},
        products={"marketplace": "Площадка", "sku": "Артикул", "url": "Ссылка", "name": "Название"},
    )

    result = await connection.preview_source(endpoint)

    assert result["products"] == [
        {"marketplace": "ozon", "sku": "2", "url": "https://x/2", "name": "Товар Б"}
    ]


async def test_columns_lists_csv_header(tmp_path) -> None:
    path = tmp_path / "products.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b", "c"])

    endpoint = EndpointConfig(kind="csv", params={"products_path": str(path)})

    header = await connection.columns(endpoint, table="products")

    assert header == ["a", "b", "c"]


def test_mask_database_url_hides_password() -> None:
    masked = connection.mask_database_url("postgresql+asyncpg://user:secret@host:5432/db")

    assert masked is not None
    assert "secret" not in masked
    assert "user" in masked
    assert "host:5432/db" in masked


def test_mask_database_url_none_stays_none() -> None:
    assert connection.mask_database_url(None) is None


def test_resolve_database_url_empty_keeps_stored() -> None:
    assert connection.resolve_database_url(None, "postgresql://old") == "postgresql://old"
    assert connection.resolve_database_url("", "postgresql://old") == "postgresql://old"
    assert connection.resolve_database_url("postgresql://new", "postgresql://old") == "postgresql://new"


def test_with_masked_database_url_masks_endpoint_params() -> None:
    endpoint = EndpointConfig(kind="db", params={"database_url": "postgresql://user:pw@host/db"})

    masked = connection.with_masked_database_url(endpoint)

    assert masked is not None
    assert "pw" not in masked.params["database_url"]


def test_build_product_source_matches_make_product_source(tmp_path) -> None:
    io_path = tmp_path / "io.json"
    io_path.write_text(
        json.dumps(
            {
                "source": {
                    "kind": "csv",
                    "products_path": "products.csv",
                    "mapping": {"products": {"sku": "SKU"}},
                }
            }
        )
    )
    settings = Settings(io_config_path=str(io_path))

    endpoint = connection.load(settings).source
    assert endpoint is not None

    assert type(build_product_source(endpoint)) is type(make_product_source(settings))


def test_build_result_sink_matches_make_result_sink(tmp_path) -> None:
    io_path = tmp_path / "io.json"
    io_path.write_text(
        json.dumps({"sink": {"kind": "csv", "path": "out.csv", "mapping": {"results": {"sku": "SKU"}}}})
    )
    settings = Settings(io_config_path=str(io_path))

    endpoint = connection.load(settings).sink
    assert endpoint is not None

    assert type(build_result_sink(endpoint)) is type(make_result_sink(settings))
