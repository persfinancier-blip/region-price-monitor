"""SQL source/sink (ADR-0010, SPEC-panel §5.1/§5.3) over SQLAlchemy — `canonical -> column`.

Mirrors `app/storage/postgres.py`'s optionality: this module is only imported
by `app/io/factory.py` when `kind: db` is actually selected, so a file-backend
config never pulls in a DB driver. Connection params (a `database_url`, plus
`products_table`/`regions_table`/`results_table`) live in plain local config
per ADR-0009 — no secret store.
"""

from typing import Any

from sqlalchemy import MetaData, Table, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.io.base import REQUIRED_PRODUCT_FIELDS, Mapping
from app.io.mapping import apply_mapping, reverse_apply_mapping, validate


class DbProductSource:
    """Reads a source table for products and one for regions through `canonical -> column`."""

    def __init__(
        self,
        database_url: str,
        products_table: str | None,
        regions_table: str | None,
        products_mapping: Mapping | None,
        regions_mapping: Mapping | None,
    ) -> None:
        self._database_url = database_url
        self._products_table = products_table
        self._regions_table = regions_table
        self._products_mapping = products_mapping or {}
        self._regions_mapping = regions_mapping or {}

    async def _read_table(
        self, table_name: str, mapping: Mapping, required: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        engine = create_async_engine(self._database_url)

        def _reflect(sync_conn: Any) -> Table:
            return Table(table_name, MetaData(), autoload_with=sync_conn)

        try:
            async with engine.connect() as conn:
                table = await conn.run_sync(_reflect)
                header = [col.name for col in table.columns]
                validate(mapping, header, required=required)
                result = await conn.execute(select(table))
                rows = [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()
        return [apply_mapping(mapping, row) for row in rows]

    async def read_products(self) -> list[dict[str, Any]]:
        if not self._products_table:
            return []
        return await self._read_table(self._products_table, self._products_mapping, REQUIRED_PRODUCT_FIELDS)

    async def read_regions(self) -> list[dict[str, Any]]:
        if not self._regions_table:
            return []
        return await self._read_table(self._regions_table, self._regions_mapping, ())


class DbResultSink:
    """Writes canonical result rows to a results table through the `canonical -> column` mapping."""

    def __init__(self, database_url: str, table_name: str, mapping: Mapping) -> None:
        self._database_url = database_url
        self._table_name = table_name
        self._mapping = mapping

    async def write_snapshots(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0

        engine = create_async_engine(self._database_url)
        try:
            async with engine.begin() as conn:
                metadata = MetaData()
                table = await conn.run_sync(
                    lambda sync_conn: Table(self._table_name, metadata, autoload_with=sync_conn)
                )
                mapped_rows = [reverse_apply_mapping(self._mapping, row) for row in rows]
                await conn.execute(insert(table), mapped_rows)
        finally:
            await engine.dispose()
        return len(rows)
