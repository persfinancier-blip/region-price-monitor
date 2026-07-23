"""app.io.factory — make_product_source/make_result_sink pick the impl by `kind`."""

import json

from app.config import Settings
from app.io.csv_io import CsvProductSource, CsvResultSink
from app.io.factory import make_product_source, make_result_sink
from app.io.json_source import JsonProductSource


def test_make_product_source_defaults_to_json_when_no_config(tmp_path) -> None:
    settings = Settings(io_config_path=str(tmp_path / "missing.json"))

    source = make_product_source(settings)

    assert isinstance(source, JsonProductSource)


def test_make_result_sink_returns_none_when_no_config(tmp_path) -> None:
    settings = Settings(io_config_path=str(tmp_path / "missing.json"))

    assert make_result_sink(settings) is None


def test_make_product_source_picks_csv_by_kind(tmp_path) -> None:
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

    source = make_product_source(settings)

    assert isinstance(source, CsvProductSource)


def test_make_result_sink_picks_csv_by_kind(tmp_path) -> None:
    io_path = tmp_path / "io.json"
    io_path.write_text(
        json.dumps({"sink": {"kind": "csv", "path": "out.csv", "mapping": {"results": {"sku": "SKU"}}}})
    )
    settings = Settings(io_config_path=str(io_path))

    sink = make_result_sink(settings)

    assert isinstance(sink, CsvResultSink)
