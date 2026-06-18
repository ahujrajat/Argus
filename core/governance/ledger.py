from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.db.tables import CostLedgerEntryRow
from core.model.entities import CostLedgerEntry
import structlog

log = structlog.get_logger()


class CostLedger:
    async def record(self, entry: CostLedgerEntry, session: AsyncSession) -> None:
        row = CostLedgerEntryRow(
            id=str(entry.id),
            scope_type=entry.scope_type,
            scope_id=str(entry.scope_id),
            tokens_in=entry.tokens_in,
            tokens_out=entry.tokens_out,
            cache_hits=entry.cache_hits,
            tier=entry.tier.value,
            provider=entry.provider,
            model_id=entry.model_id,
            batch_flag=entry.batch_flag,
            cost_usd=entry.cost_usd,
            timestamp=entry.timestamp,
        )
        session.add(row)
        await session.flush()
        log.info(
            "cost_ledger_entry",
            scope_type=entry.scope_type,
            scope_id=str(entry.scope_id),
            cost_usd=entry.cost_usd,
            model_id=entry.model_id,
        )

    async def scan_summary(self, scan_id: UUID, session: AsyncSession) -> dict:
        result = await session.execute(
            select(
                func.sum(CostLedgerEntryRow.cost_usd).label("total_cost_usd"),
                func.sum(CostLedgerEntryRow.tokens_in).label("total_tokens_in"),
                func.sum(CostLedgerEntryRow.tokens_out).label("total_tokens_out"),
                func.sum(CostLedgerEntryRow.cache_hits).label("total_cache_hits"),
                func.count().label("call_count"),
            ).where(
                CostLedgerEntryRow.scope_id == str(scan_id),
                CostLedgerEntryRow.scope_type == "scan",
            )
        )
        row = result.one()
        return {
            "total_cost_usd": float(row.total_cost_usd or 0),
            "total_tokens_in": int(row.total_tokens_in or 0),
            "total_tokens_out": int(row.total_tokens_out or 0),
            "total_cache_hits": int(row.total_cache_hits or 0),
            "call_count": int(row.call_count or 0),
        }
