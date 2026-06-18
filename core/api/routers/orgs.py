# core/api/routers/orgs.py
from __future__ import annotations
import re
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import OrgRow, OrgMemberRow

router = APIRouter(prefix="/orgs", tags=["orgs"])

_SLUG_RE = re.compile(r'^[a-z0-9-]+$')


class CreateOrgRequest(BaseModel):
    name: str
    slug: str

    @field_validator("slug")
    @classmethod
    def slug_must_be_valid(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("slug must match ^[a-z0-9-]+$")
        return v


class AddMemberRequest(BaseModel):
    user_id: str
    role: Literal["admin", "analyst", "viewer"]


def _org_to_dict(r: OrgRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "slug": r.slug,
        "created_at": r.created_at,
    }


def _member_to_dict(r: OrgMemberRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "org_id": r.org_id,
        "user_id": r.user_id,
        "role": r.role,
        "created_at": r.created_at,
    }


@router.post("/", status_code=201)
async def create_org(
    body: CreateOrgRequest,
    db: AsyncSession = Depends(get_db),
):
    row = OrgRow(
        id=str(uuid4()),
        name=body.name,
        slug=body.slug,
    )
    db.add(row)
    await db.flush()
    return _org_to_dict(row)


@router.get("/")
async def list_orgs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrgRow).order_by(OrgRow.created_at.desc()))
    return [_org_to_dict(r) for r in result.scalars().all()]


@router.get("/{org_id}")
async def get_org(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrgRow).where(OrgRow.id == org_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Org not found")
    return _org_to_dict(row)


@router.delete("/{org_id}", status_code=200)
async def delete_org(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrgRow).where(OrgRow.id == org_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Org not found")
    await db.delete(row)
    await db.flush()
    return {"id": org_id, "status": "deleted"}


@router.post("/{org_id}/members", status_code=201)
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify org exists
    result = await db.execute(select(OrgRow).where(OrgRow.id == org_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Org not found")

    member = OrgMemberRow(
        id=str(uuid4()),
        org_id=org_id,
        user_id=body.user_id,
        role=body.role,
    )
    db.add(member)
    await db.flush()
    return _member_to_dict(member)


@router.get("/{org_id}/members")
async def list_members(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OrgMemberRow).where(OrgMemberRow.org_id == org_id).order_by(OrgMemberRow.created_at.desc())
    )
    return [_member_to_dict(r) for r in result.scalars().all()]


@router.delete("/{org_id}/members/{member_id}", status_code=200)
async def remove_member(
    org_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMemberRow).where(OrgMemberRow.id == member_id, OrgMemberRow.org_id == org_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(row)
    await db.flush()
    return {"id": member_id, "status": "deleted"}
