"""app.io.csv_io — round-trip with a non-canonical header; Decimal prices survive as strings."""

import csv
from decimal import Decimal

from app.io.csv_io import CsvProductSource, CsvResultSink


async def test_csv_product_source_maps_non_canonical_header_to_canonical(tmp_path) -> None:
    products_path = tmp_path / "products.csv"
    products_path.write_text(
        "Площадка,Артикул,Ссылка,Название\nwb,12345,https://x/1,Товар А\n", encoding="utf-8"
    )

    source = CsvProductSource(
        products_path=str(products_path),
        regions_path=None,
        products_mapping={
            "marketplace": "Площадка",
            "sku": "Артикул",
            "url": "Ссылка",
            "name": "Название",
        },
        regions_mapping=None,
    )

    rows = await source.read_products()

    assert rows == [
        {"marketplace": "wb", "sku": "12345", "url": "https://x/1", "name": "Товар А"},
    ]


async def test_csv_result_sink_writes_mapped_columns_with_decimal_price_as_string(tmp_path) -> None:
    out_path = tmp_path / "results.csv"
    sink = CsvResultSink(
        path=str(out_path),
        mapping={"sku": "SKU", "price": "Цена", "status": "Статус"},
    )

    written = await sink.write_snapshots([{"sku": "12345", "price": Decimal("199.90"), "status": "ok"}])

    assert written == 1
    with open(out_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [{"SKU": "12345", "Цена": "199.90", "Статус": "ok"}]
