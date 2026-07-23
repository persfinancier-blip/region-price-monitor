"""app.io.json_source — the default JSON source reproduces today's import exactly."""

import json

from app.io.json_source import JsonProductSource, JsonResultSink


async def test_json_product_source_reads_products_file_unchanged(tmp_path) -> None:
    path = tmp_path / "products.json"
    items = [{"marketplace": "wb", "sku": "12345", "url": "https://x/1", "name": "A"}]
    path.write_text(json.dumps(items), encoding="utf-8")

    source = JsonProductSource(products_path=str(path), regions_path=None)

    assert await source.read_products() == items


async def test_json_product_source_reads_regions_file_unchanged(tmp_path) -> None:
    path = tmp_path / "regions.json"
    items = [{"code": "msk", "name": "Moscow", "geo": {"wb": {"dest": 1}}}]
    path.write_text(json.dumps(items), encoding="utf-8")

    source = JsonProductSource(products_path=None, regions_path=str(path))

    assert await source.read_regions() == items


async def test_json_product_source_no_path_configured_returns_empty() -> None:
    source = JsonProductSource(products_path=None, regions_path=None)

    assert await source.read_products() == []
    assert await source.read_regions() == []


async def test_json_result_sink_writes_rows(tmp_path) -> None:
    path = tmp_path / "out.json"
    sink = JsonResultSink(path=str(path))

    written = await sink.write_snapshots([{"sku": "12345", "price": "199.90"}])

    assert written == 1
    assert json.loads(path.read_text(encoding="utf-8")) == [{"sku": "12345", "price": "199.90"}]
