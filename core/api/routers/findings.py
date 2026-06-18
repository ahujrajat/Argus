# core/api/routers/findings.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import FindingRow

router = APIRouter(prefix="/scans", tags=["findings"])


@router.get("/{scan_id}/findings")
async def list_findings(
    scan_id: UUID,
    severity: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    if severity:
        q = q.where(FindingRow.severity == severity)
    if status:
        q = q.where(FindingRow.status == status)
    q = q.order_by(FindingRow.exploit_likelihood.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "rule_id": r.rule_id, "source_tool": r.source_tool,
            "cwe": r.cwe, "owasp_category": r.owasp_category,
            "severity": r.severity, "confidence": r.confidence,
            "exploit_likelihood": r.exploit_likelihood,
            "reachability": r.reachability,
            "location": r.location, "status": r.status,
            "explanation": r.explanation,
        }
        for r in rows
    ]
