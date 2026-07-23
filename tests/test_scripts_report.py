"""app.scripts.report — argv smoke test (no DB) + DB-backed run() tests (skip cleanly without Postgres)."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import make_engine
from app.enums import Marketplace
from app.repositories import ProductRepository, RegionRepository
from app.scripts import report


def test_main_requires_run_or_last() -> None:
    with pytest.raises(SystemExit) as exc_info:
        report.main([])
    assert exc_info.value.code != 0


def test_main_help_smoke() -> None:
    with pytest.raises(SystemExit) as exc_info:
        report.main(["--help"])
    assert exc_info.value.code == 0


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

if not TEST_DATABASE_URL:
    pytest.skip("no TEST_DATABASE_URL/DATABASE_URL configured", allow_module_level=True)

try:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        capture_output=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
    )
except (subprocess.CalledProcessError, FileNotFoundError) as exc:
    pytest.skip(f"database unreachable: {exc}", allow_module_level=True)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"database unreachable: {exc}")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()
    await engine.dispose()


async def _seed_run(session: AsyncSession):
    from app.enums import Outcome, RunMode

    product_repo = ProductRepository(session)
    region_repo = RegionRepository(session)
    from app.repositories import AttemptRepository, MeasureQueueRepository, RunRepository

    run_repo = RunRepository(session)
    queue_repo = MeasureQueueRepository(session)
    attempt_repo = AttemptRepository(session)

    product = await product_repo.upsert(
        marketplace=Marketplace.WB, sku="report-test-sku", url="https://example.com/p", name="P"
    )
    region = await region_repo.upsert(code="report-test-region", name="R", geo={"wb": {"dest": 1}})
    run_row = await run_repo.create(mode=RunMode.MANUAL)
    await session.flush()

    queue_item = await queue_repo.create(run_id=run_row.id, product_id=product.id, region_id=region.id)
    await attempt_repo.add(
        queue_id=queue_item.id, proxy_ref="static:x:host", outcome=Outcome.OK, duration_ms=100
    )
    await session.flush()
    return run_row.id


async def test_run_prints_summary_for_explicit_run_id(session: AsyncSession, capsys) -> None:
    run_id = await _seed_run(session)

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    result = await report.run(run_id, False, session_factory=fake_session_factory)

    assert result == 0
    out = capsys.readouterr().out
    assert f"run {run_id}:" in out
    assert "rpm_run_success_rate" in out


async def test_run_last_resolves_most_recent_run(session: AsyncSession, capsys) -> None:
    run_id = await _seed_run(session)

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    result = await report.run(None, True, session_factory=fake_session_factory)

    assert result == 0
    out = capsys.readouterr().out
    assert f"run {run_id}:" in out


async def test_run_missing_run_reports_error(session: AsyncSession) -> None:
    @asynccontextmanager
    async def fake_session_factory():
        yield session

    result = await report.run(None, False, session_factory=fake_session_factory)

    assert result == 1
