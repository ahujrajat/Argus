# core/api/routers/auth.py
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.auth.keys import generate_key, require_api_key
from core.db.tables import ApiKeyRow

router = APIRouter(prefix="/auth", tags=["auth"])


class CreateKeyRequest(BaseModel):
    name: str
    created_by: str = "api"
    expires_at: datetime | None = None


@router.post("/keys", status_code=201)
async def create_api_key(
    body: CreateKeyRequest,
    db: AsyncSession = Depends(get_db),
):
    raw, hashed = generate_key()
    row = ApiKeyRow(
        id=str(uuid4()),
        name=body.name,
        key_hash=hashed,
        created_by=body.created_by,
        expires_at=body.expires_at,
    )
    db.add(row)
    await db.flush()
    return {
        "id": row.id,
        "name": row.name,
        "key": raw,  # only returned once — not stored
        "created_at": row.created_at,
        "expires_at": row.expires_at,
    }


@router.get("/keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _: ApiKeyRow = Depends(require_api_key),
):
    result = await db.execute(
        select(ApiKeyRow).where(ApiKeyRow.revoked == False).order_by(ApiKeyRow.created_at.desc())  # noqa: E712
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "created_by": r.created_by,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
        }
        for r in rows
    ]


@router.delete("/keys/{key_id}", status_code=200)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _: ApiKeyRow = Depends(require_api_key),
):
    result = await db.execute(select(ApiKeyRow).where(ApiKeyRow.id == key_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="API key not found")
    if row.revoked:
        raise HTTPException(status_code=409, detail="API key already revoked")
    row.revoked = True
    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": key_id, "status": "revoked"}
