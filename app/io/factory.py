"""`make_product_source(settings)` / `make_result_sink(settings)` — I/O factory (ADR-0010).

Picks a concrete `ProductSource`/`ResultSink` by `kind` from `settings.io_config_path`
(`json` | `csv` | `xlsx` | `db`), mirroring `app/storage/factory.py`'s style. No
`io.json` ⇒ local-first defaults: a JSON product source (unconfigured, i.e. no
files — callers pass an explicit path the old way) and no sink at all.
"""

from app.config import Settings
from app.io.base import ProductSource, ResultSink
from app.io.mapping import EndpointConfig, load_io_config


def make_product_source(settings: Settings) -> ProductSource:
    """Return the configured `ProductSource`; defaults to an unconfigured JSON source."""
    config = load_io_config(settings.io_config_path)
    if config.source is None:
        from app.io.json_source import JsonProductSource

        return JsonProductSource(products_path=None, regions_path=None)

    return _build_product_source(config.source)


def make_result_sink(settings: Settings) -> ResultSink | None:
    """Return the configured `ResultSink`, or `None` if no sink is configured."""
    config = load_io_config(settings.io_config_path)
    if config.sink is None:
        return None

    return _build_result_sink(config.sink)


def _build_product_source(endpoint: EndpointConfig) -> ProductSource:
    if endpoint.kind == "json":
        from app.io.json_source import JsonProductSource

        return JsonProductSource(
            products_path=endpoint.params.get("products_path"),
            regions_path=endpoint.params.get("regions_path"),
        )

    if endpoint.kind == "csv":
        from app.io.csv_io import CsvProductSource

        return CsvProductSource(
            products_path=endpoint.params.get("products_path"),
            regions_path=endpoint.params.get("regions_path"),
            products_mapping=endpoint.products,
            regions_mapping=endpoint.regions,
        )

    if endpoint.kind == "xlsx":
        from app.io.xlsx_io import XlsxProductSource

        products = endpoint.params.get("products", {})
        regions = endpoint.params.get("regions", {})
        return XlsxProductSource(
            products_path=products.get("path"),
            products_sheet=products.get("sheet"),
            products_range=products.get("range"),
            regions_path=regions.get("path"),
            regions_sheet=regions.get("sheet"),
            regions_range=regions.get("range"),
            products_mapping=endpoint.products,
            regions_mapping=endpoint.regions,
        )

    if endpoint.kind == "db":
        from app.io.db_io import DbProductSource

        return DbProductSource(
            database_url=endpoint.params["database_url"],
            products_table=endpoint.params.get("products_table"),
            regions_table=endpoint.params.get("regions_table"),
            products_mapping=endpoint.products,
            regions_mapping=endpoint.regions,
        )

    raise ValueError(f"unknown io source kind: {endpoint.kind!r}")


def _build_result_sink(endpoint: EndpointConfig) -> ResultSink:
    if endpoint.kind == "json":
        from app.io.json_source import JsonResultSink

        return JsonResultSink(path=endpoint.params["path"])

    if endpoint.kind == "csv":
        from app.io.csv_io import CsvResultSink

        assert endpoint.results is not None, "csv sink requires a `results` mapping"
        return CsvResultSink(path=endpoint.params["path"], mapping=endpoint.results)

    if endpoint.kind == "xlsx":
        from app.io.xlsx_io import XlsxResultSink

        assert endpoint.results is not None, "xlsx sink requires a `results` mapping"
        return XlsxResultSink(
            path=endpoint.params["path"], sheet=endpoint.params.get("sheet"), mapping=endpoint.results
        )

    if endpoint.kind == "db":
        from app.io.db_io import DbResultSink

        assert endpoint.results is not None, "db sink requires a `results` mapping"
        return DbResultSink(
            database_url=endpoint.params["database_url"],
            table_name=endpoint.params["results_table"],
            mapping=endpoint.results,
        )

    raise ValueError(f"unknown io sink kind: {endpoint.kind!r}")
