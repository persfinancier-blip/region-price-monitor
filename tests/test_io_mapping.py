"""app.io.mapping — config load, validate() (unknown/missing/shifted), preview()."""

import json

import pytest

from app.io.mapping import (
    MappingError,
    apply_mapping,
    load_io_config,
    preview,
    resolve_column,
    reverse_apply_mapping,
    validate,
    validate_known_fields,
)


def test_load_io_config_missing_file_returns_none_source_and_sink(tmp_path) -> None:
    config = load_io_config(str(tmp_path / "does-not-exist.json"))

    assert config.source is None
    assert config.sink is None


def test_load_io_config_parses_source_and_sink(tmp_path) -> None:
    path = tmp_path / "io.json"
    path.write_text(
        json.dumps(
            {
                "source": {
                    "kind": "csv",
                    "products_path": "products.csv",
                    "mapping": {"products": {"sku": "SKU"}},
                },
                "sink": {
                    "kind": "csv",
                    "path": "out.csv",
                    "mapping": {"results": {"sku": "SKU", "price": "Price"}},
                },
            }
        )
    )

    config = load_io_config(str(path))

    assert config.source is not None
    assert config.source.kind == "csv"
    assert config.source.params == {"products_path": "products.csv"}
    assert config.source.products == {"sku": "SKU"}
    assert config.sink is not None
    assert config.sink.results == {"sku": "SKU", "price": "Price"}


def test_validate_flags_missing_required_fields() -> None:
    mapping = {"sku": "SKU"}
    header = ["SKU", "URL", "Name"]

    with pytest.raises(MappingError, match="missing required fields"):
        validate(mapping, header, required=("sku", "url", "name"))


def test_validate_flags_shifted_columns_absent_from_header() -> None:
    mapping = {"sku": "SKU", "url": "URL_MOVED"}
    header = ["SKU", "URL", "Name"]

    with pytest.raises(MappingError, match="locators absent from source header"):
        validate(mapping, header, required=("sku",))


def test_validate_passes_when_mapping_matches_header() -> None:
    mapping = {"sku": "SKU", "url": "URL"}
    header = ["SKU", "URL", "Name"]

    validate(mapping, header, required=("sku", "url"))


def test_validate_known_fields_flags_unknown_canonical_field() -> None:
    with pytest.raises(MappingError, match="unknown canonical fields"):
        validate_known_fields({"sku": "SKU", "bogus_field": "X"}, known_fields=("sku", "url", "name"))


def test_apply_and_reverse_apply_mapping_roundtrip() -> None:
    mapping = {"sku": "SKU", "price": "Price"}
    native_row = {"SKU": "abc123", "Price": "199.90"}

    canonical_row = apply_mapping(mapping, native_row)
    assert canonical_row == {"sku": "abc123", "price": "199.90"}

    back = reverse_apply_mapping(mapping, canonical_row)
    assert back == native_row


def test_preview_returns_first_n_mapped_rows() -> None:
    mapping = {"sku": "SKU"}
    rows = [{"SKU": str(i)} for i in range(10)]

    result = preview(rows, mapping, n=3)

    assert result == [{"sku": "0"}, {"sku": "1"}, {"sku": "2"}]


def test_resolve_column_by_header_name() -> None:
    assert resolve_column("Price", ["SKU", "Price"]) == 1


def test_resolve_column_by_letter() -> None:
    assert resolve_column("A", ["x", "y"]) == 0
    assert resolve_column("B", ["x", "y"]) == 1


def test_resolve_column_unresolvable_raises() -> None:
    with pytest.raises(MappingError):
        resolve_column("123", ["x", "y"])
