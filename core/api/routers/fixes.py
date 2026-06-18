# core/api/routers/fixes.py
from __future__ import annotations
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import FixRow, FindingRow, AuditLogEntryRow

router = APIRouter(tags=["fixes"])


class RejectBody(BaseModel):
    reason: str


@router.get("/scans/{scan_id}/fixes")
async def list_scan_fixes(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(FixRow)
        .join(FindingRow, FixRow.finding_id == FindingRow.id)
        .where(FindingRow.scan_id == str(scan_id))
    )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "finding_id": r.finding_id,
            "diff": r.diff,
            "test": r.test,
            "explanation": r.explanation,
            "validation_result": r.validation_result,
            "status": r.status,
            "reviewer": r.reviewer,
            "audit_ref": r.audit_ref,
        }
        for r in rows
    ]


@router.get("/fixes/{fix_id}")
async def get_fix(fix_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "diff": row.diff,
        "test": row.test,
        "explanation": row.explanation,
        "validation_result": row.validation_result,
        "status": row.status,
        "reviewer": row.reviewer,
        "audit_ref": row.audit_ref,
    }


@router.post("/fixes/{fix_id}/apply")
async def apply_fix(fix_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Write audit log BEFORE mutating status
    audit = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="fix_apply",
        target=str(fix_id),
        before={"status": row.status},
        after={"status": "applied"},
    )
    db.add(audit)

    row.status = "applied"
    await db.commit()
    await db.refresh(row)
    return {"status": row.status, "fix_id": str(fix_id)}


@router.post("/fixes/{fix_id}/reject")
async def reject_fix(
    fix_id: UUID,
    body: RejectBody,
    db: AsyncSession = Depends(get_db),
):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Write audit log BEFORE mutating status
    audit = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="fix_reject",
        target=str(fix_id),
        before={"status": row.status},
        after={"status": "rejected", "reason": body.reason},
    )
    db.add(audit)

    row.status = "rejected"
    await db.commit()
    await db.refresh(row)
    return {"status": row.status, "fix_id": str(fix_id)}
