# core/api/routers/cost.py
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.api.deps import get_db
from core.db.tables import CostLedgerEntryRow

router = APIRouter(prefix="/cost", tags=["cost"])


@router.get("/ledger")
async def get_ledger(
    scope_type: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(CostLedgerEntryRow).order_by(CostLedgerEntryRow.timestamp.desc()).limit(limit)
    if scope_type:
        q = q.where(CostLedgerEntryRow.scope_type == scope_type)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {"id": r.id, "scope_type": r.scope_type, "scope_id": r.scope_id,
         "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
         "tier": r.tier, "provider": r.provider, "model_id": r.model_id,
         "cost_usd": r.cost_usd, "timestamp": r.timestamp}
        for r in rows
    ]


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.sum(CostLedgerEntryRow.cost_usd).label("total_cost_usd"),
            func.sum(CostLedgerEntryRow.tokens_in).label("total_tokens_in"),
            func.sum(CostLedgerEntryRow.tokens_out).label("total_tokens_out"),
            func.count().label("total_calls"),
        )
    )
    row = result.one()
    return {
        "total_cost_usd": float(row.total_cost_usd or 0),
        "total_tokens_in": int(row.total_tokens_in or 0),
        "total_tokens_out": int(row.total_tokens_out or 0),
        "total_calls": int(row.total_calls or 0),
    }
