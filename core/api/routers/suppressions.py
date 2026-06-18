# core/api/routers/suppressions.py
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import SuppressionRuleRow

router = APIRouter(prefix="/suppressions", tags=["suppressions"])

PatternType = Literal["fingerprint", "path_glob", "rule_id"]


class CreateSuppressionRequest(BaseModel):
    pattern_type: PatternType
    pattern: str
    reason: str | None = None
    created_by: str = "api"
    expires_at: datetime | None = None

    @field_validator("pattern")
    @classmethod
    def pattern_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("pattern must not be empty")
        return v


@router.post("/", status_code=201)
async def create_suppression(
    body: CreateSuppressionRequest,
    db: AsyncSession = Depends(get_db),
):
    row = SuppressionRuleRow(
        id=str(uuid4()),
        pattern_type=body.pattern_type,
        pattern=body.pattern,
        reason=body.reason,
        created_by=body.created_by,
        expires_at=body.expires_at,
    )
    db.add(row)
    await db.flush()
    return {
        "id": row.id,
        "pattern_type": row.pattern_type,
        "pattern": row.pattern,
        "reason": row.reason,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


@router.get("/")
async def list_suppressions(
    include_expired: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SuppressionRuleRow).order_by(SuppressionRuleRow.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    now = datetime.now(timezone.utc)

    out = []
    for r in rows:
        active = r.expires_at is None or r.expires_at > now
        if not include_expired and not active:
            continue
        out.append({
            "id": r.id,
            "pattern_type": r.pattern_type,
            "pattern": r.pattern,
            "reason": r.reason,
            "created_by": r.created_by,
            "expires_at": r.expires_at,
            "created_at": r.created_at,
            "active": active,
        })
    return out


@router.delete("/{rule_id}", status_code=200)
async def delete_suppression(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SuppressionRuleRow).where(SuppressionRuleRow.id == rule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Suppression rule not found")
    await db.delete(row)
    await db.flush()
    return {"id": rule_id, "status": "deleted"}
