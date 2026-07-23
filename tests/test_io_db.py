"""app.io.db_io — SQL source/sink round-trip; requires a real Postgres, skips cleanly without one."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import make_engine
from app.io.db_io import DbProductSource, DbResultSink

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

if not TEST_DATABASE_URL:
    pytest.skip("no TEST_DATABASE_URL/DATABASE_URL configured", allow_module_level=True)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine(TEST_DATABASE_URL)
    try:
        async with eng.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"database unreachable: {exc}")

    async with eng.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS io_test_source_products"))
        await conn.execute(text("DROP TABLE IF EXISTS io_test_results"))
        await conn.execute(
            text("CREATE TABLE io_test_source_products (mp TEXT, sku TEXT, url TEXT, title TEXT)")
        )
        await conn.execute(
            text(
                "CREATE TABLE io_test_results (sku TEXT, region_code TEXT, price TEXT, ts TEXT, status TEXT)"
            )
        )
        await conn.execute(
            text("INSERT INTO io_test_source_products VALUES ('wb', '12345', 'https://x/1', 'Товар А')")
        )

    yield eng

    async with eng.begin() as conn:
        await conn.execute(text("DROP TABLE io_test_source_products"))
        await conn.execute(text("DROP TABLE io_test_results"))
    await eng.dispose()


async def test_db_product_source_maps_table_columns_to_canonical(engine: AsyncEngine) -> None:
    source = DbProductSource(
        database_url=TEST_DATABASE_URL,
        products_table="io_test_source_products",
        regions_table=None,
        products_mapping={"marketplace": "mp", "sku": "sku", "url": "url", "name": "title"},
        regions_mapping=None,
    )

    rows = await source.read_products()

    assert rows == [{"marketplace": "wb", "sku": "12345", "url": "https://x/1", "name": "Товар А"}]


async def test_db_result_sink_writes_mapped_columns(engine: AsyncEngine) -> None:
    sink = DbResultSink(
        database_url=TEST_DATABASE_URL,
        table_name="io_test_results",
        mapping={
            "sku": "sku",
            "region": "region_code",
            "price": "price",
            "measured_at": "ts",
            "status": "status",
        },
    )

    written = await sink.write_snapshots(
        [
            {
                "sku": "12345",
                "region": "msk",
                "price": "199.90",
                "measured_at": "2026-07-23T00:00:00",
                "status": "ok",
            }
        ]
    )

    assert written == 1

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT sku, region_code, price, status FROM io_test_results"))
        rows = result.all()

    assert rows == [("12345", "msk", "199.90", "ok")]
