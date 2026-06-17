# tests/core/test_db.py
from __future__ import annotations
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.session import get_session, engine
from core.db.tables import Base

@pytest.fixture(scope="module")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def test_session_is_async(db_session: AsyncSession):
    assert isinstance(db_session, AsyncSession)

async def test_tables_exist(db_session: AsyncSession):
    from sqlalchemy import text
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    tables = {row[0] for row in result}
    assert "scans" in tables
    assert "findings" in tables
    assert "cost_ledger_entries" in tables
    assert "audit_log_entries" in tables
    assert "pipeline_configs" in tables
