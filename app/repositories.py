"""Async repositories for reference-data tables (idempotent upserts)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Marketplace
from app.models import Product, Region


class ProductRepository:
    """Repository for the `products` reference table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        marketplace: Marketplace,
        sku: str,
        url: str,
        name: str,
        is_active: bool = True,
    ) -> Product:
        """Insert or update a product, keyed on (marketplace, sku)."""
        stmt = (
            insert(Product)
            .values(marketplace=marketplace, sku=sku, url=url, name=name, is_active=is_active)
            .on_conflict_do_update(
                index_elements=[Product.marketplace, Product.sku],
                set_={"url": url, "name": name, "is_active": is_active},
            )
            .returning(Product)
        )
        result = await self._session.execute(stmt, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def list_active(self) -> list[Product]:
        """Return all active products."""
        result = await self._session.execute(select(Product).where(Product.is_active.is_(True)))
        return list(result.scalars().all())


class RegionRepository:
    """Repository for the `regions` reference table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        code: str,
        name: str,
        geo: dict[str, Any],
        is_active: bool = True,
    ) -> Region:
        """Insert or update a region, keyed on code."""
        stmt = (
            insert(Region)
            .values(code=code, name=name, geo=geo, is_active=is_active)
            .on_conflict_do_update(
                index_elements=[Region.code],
                set_={"name": name, "geo": geo, "is_active": is_active},
            )
            .returning(Region)
        )
        result = await self._session.execute(stmt, execution_options={"populate_existing": True})
        return result.scalar_one()

    async def list_active(self) -> list[Region]:
        """Return all active regions."""
        result = await self._session.execute(select(Region).where(Region.is_active.is_(True)))
        return list(result.scalars().all())
