"""app.scripts.connection — db-backed `columns`/`validate_source`; skips cleanly without a DB."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import make_engine
from app.io.mapping import EndpointConfig
from app.scripts import connection

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
        await conn.execute(text("DROP TABLE IF EXISTS conn_test_source_products"))
        await conn.execute(text("CREATE TABLE conn_test_source_products (mp TEXT, sku TEXT)"))

    yield eng

    async with eng.begin() as conn:
        await conn.execute(text("DROP TABLE conn_test_source_products"))
    await eng.dispose()


async def test_columns_lists_db_table_columns(engine: AsyncEngine) -> None:
    endpoint = EndpointConfig(
        kind="db",
        params={"database_url": TEST_DATABASE_URL, "products_table": "conn_test_source_products"},
    )

    header = await connection.columns(endpoint, table="products")

    assert header == ["mp", "sku"]
