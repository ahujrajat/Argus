from __future__ import annotations
import pytest
from uuid import uuid4
from core.governance.ledger import CostLedger
from core.model.entities import CostLedgerEntry, ModelTier

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session():
    # Use in-memory SQLite for unit tests — only create the cost_ledger_entries
    # table to avoid JSONB incompatibility from other PostgreSQL-specific tables.
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.db.tables import CostLedgerEntryRow
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CostLedgerEntryRow.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_record_and_retrieve(session):
    ledger = CostLedger()
    scan_id = uuid4()
    entry = CostLedgerEntry(
        scope_type="scan",
        scope_id=scan_id,
        tokens_in=1000,
        tokens_out=200,
        tier=ModelTier.balanced,
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        cost_usd=0.006,
    )
    await ledger.record(entry, session)
    summary = await ledger.scan_summary(scan_id, session)
    assert summary["total_cost_usd"] == pytest.approx(0.006)
    assert summary["total_tokens_in"] == 1000
