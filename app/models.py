"""SQLAlchemy 2.x ORM models — the persistent data model."""

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import desc as sa_desc
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import Marketplace, Outcome, QueueStatus, RunMode, RunStatus


def _pg_enum(enum_cls: type, name: str) -> PgEnum:
    return PgEnum(enum_cls, name=name, values_callable=lambda e: [member.value for member in e])


class Product(Base):
    """A tracked marketplace product (SKU)."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("marketplace", "sku", name="uq_products_marketplace_sku"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    marketplace: Mapped[Marketplace] = mapped_column(_pg_enum(Marketplace, "marketplace"), nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Region(Base):
    """A geographic region used to price-check via a regional proxy."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    geo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Run(Base):
    """A single measurement run (scheduled or manual)."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mode: Mapped[RunMode] = mapped_column(_pg_enum(RunMode, "run_mode"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(_pg_enum(RunStatus, "run_status"), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class MeasureQueueItem(Base):
    """A pending/in-flight (product, region) measurement within a run."""

    __tablename__ = "measure_queue"
    __table_args__ = (Index("ix_measure_queue_status_run", "status", "run_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    status: Mapped[QueueStatus] = mapped_column(
        _pg_enum(QueueStatus, "queue_status"),
        nullable=False,
        default=QueueStatus.PENDING,
        server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[Run] = relationship()
    product: Mapped[Product] = relationship()
    region: Mapped[Region] = relationship()


class PriceSnapshot(Base):
    """An insert-only historical price observation."""

    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index(
            "ix_price_snapshots_product_region_captured",
            "product_id",
            "region_id",
            sa_desc("captured_at"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    captured_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_card: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    product: Mapped[Product] = relationship()
    region: Mapped[Region] = relationship()
    run: Mapped[Run] = relationship()


class Attempt(Base):
    """A diagnostic record of a single collection attempt (anti-bot / proxy outcome)."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("measure_queue.id"), nullable=False)
    proxy_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[Outcome] = mapped_column(_pg_enum(Outcome, "outcome"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    queue_item: Mapped[MeasureQueueItem] = relationship()
