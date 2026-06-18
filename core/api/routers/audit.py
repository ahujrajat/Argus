# core/api/routers/audit.py
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import AuditLogEntryRow

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/")
async def list_audit_entries(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLogEntryRow)
        .order_by(AuditLogEntryRow.timestamp.desc())
        .limit(min(limit, 500))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "actor": r.actor,
            "action": r.action,
            "target": r.target,
            "before": r.before,
            "after": r.after,
            "timestamp": r.timestamp,
        }
        for r in rows
    ]
