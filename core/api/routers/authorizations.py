from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import TargetAuthorizationRow

router = APIRouter(prefix="/authorizations", tags=["authorizations"])


class CreateAuthorizationRequest(BaseModel):
    target: str
    owner_confirmed: bool
    environment: str = "non-production"
    scope_rules: dict = {}
    rate_limits: dict = {}
    expires_at: Optional[datetime] = None

    @field_validator("owner_confirmed")
    @classmethod
    def must_be_confirmed(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "owner_confirmed must be True — explicit confirmation required "
                "before authorizing any VCS write operations against a target"
            )
        return v


@router.post("", status_code=201)
async def create_authorization(
    body: CreateAuthorizationRequest,
    db: AsyncSession = Depends(get_db),
):
    row = TargetAuthorizationRow(
        id=str(uuid4()),
        target=body.target,
        scope_rules=body.scope_rules,
        owner_confirmed=body.owner_confirmed,
        environment=body.environment,
        rate_limits=body.rate_limits,
        expires_at=body.expires_at,
    )
    db.add(row)
    await db.flush()
    return {
        "id": row.id,
        "target": row.target,
        "owner_confirmed": row.owner_confirmed,
        "environment": row.environment,
        "expires_at": row.expires_at,
    }


@router.get("")
async def list_authorizations(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    q = select(TargetAuthorizationRow).where(
        (TargetAuthorizationRow.expires_at == None)  # noqa: E711
        | (TargetAuthorizationRow.expires_at > now)
    )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "target": r.target,
            "owner_confirmed": r.owner_confirmed,
            "environment": r.environment,
            "expires_at": r.expires_at,
        }
        for r in rows
    ]


@router.delete("/{auth_id}", status_code=204)
async def revoke_authorization(
    auth_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TargetAuthorizationRow).where(
            TargetAuthorizationRow.id == str(auth_id)
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Authorization not found")
    await db.delete(row)
