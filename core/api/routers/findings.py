# core/api/routers/findings.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import FindingRow
from core.api.pagination import decode_cursor, paginate_list
from core.api.search import matches_query

router = APIRouter(prefix="/scans", tags=["findings"])


@router.get("/{scan_id}/findings")
async def list_findings(
    scan_id: UUID,
    severity: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    if severity:
        stmt = stmt.where(FindingRow.severity == severity)
    if status:
        stmt = stmt.where(FindingRow.status == status)
    if cursor:
        stmt = stmt.where(FindingRow.id > decode_cursor(cursor))
    stmt = stmt.order_by(FindingRow.id).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    items = [
        {
            "id": r.id, "rule_id": r.rule_id, "source_tool": r.source_tool,
            "cwe": r.cwe, "owasp_category": r.owasp_category,
            "severity": r.severity, "confidence": r.confidence,
            "exploit_likelihood": r.exploit_likelihood,
            "reachability": r.reachability,
            "location": r.location, "status": r.status,
            "explanation": r.explanation,
            "dedup_key": r.dedup_key,
        }
        for r in rows
    ]
    if q:
        items = [item for item in items if matches_query(item, q)]
    page = paginate_list(items, limit)
    return {"items": page.items, "next_cursor": page.next_cursor, "limit": limit}
