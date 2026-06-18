# core/api/routers/bulk.py
"""Bulk operations on findings: suppress, dismiss, assign."""
from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import FindingRow, SuppressionRuleRow
from core.suppression.engine import SuppressionRule, apply_suppressions

router = APIRouter(prefix="/findings", tags=["bulk"])

_VALID_STATUSES = {"open", "dismissed", "suppressed", "fixed"}


class BulkSuppressRequest(BaseModel):
    finding_ids: list[str]
    reason: str | None = None
    created_by: str = "api"

    @field_validator("finding_ids")
    @classmethod
    def ids_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("finding_ids must not be empty")
        if len(v) > 500:
            raise ValueError("Cannot suppress more than 500 findings at once")
        return v


class BulkDismissRequest(BaseModel):
    finding_ids: list[str]
    reason: str | None = None

    @field_validator("finding_ids")
    @classmethod
    def ids_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("finding_ids must not be empty")
        if len(v) > 500:
            raise ValueError("Cannot dismiss more than 500 findings at once")
        return v


class BulkAssignRequest(BaseModel):
    finding_ids: list[str]
    assignee: str

    @field_validator("finding_ids")
    @classmethod
    def ids_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("finding_ids must not be empty")
        if len(v) > 500:
            raise ValueError("Cannot assign more than 500 findings at once")
        return v

    @field_validator("assignee")
    @classmethod
    def assignee_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("assignee must not be empty")
        return v


async def _fetch_findings(ids: list[str], db: AsyncSession) -> list[FindingRow]:
    result = await db.execute(
        select(FindingRow).where(FindingRow.id.in_(ids))
    )
    return result.scalars().all()


@router.post("/bulk-suppress", status_code=200)
async def bulk_suppress(body: BulkSuppressRequest, db: AsyncSession = Depends(get_db)):
    """
    Suppress a list of findings by fingerprint.
    Creates a SuppressionRuleRow for each finding's dedup_key and marks the finding suppressed.
    """
    from uuid import uuid4

    rows = await _fetch_findings(body.finding_ids, db)
    if not rows:
        raise HTTPException(status_code=404, detail="No findings found for given IDs")

    suppressed_ids: list[str] = []
    skipped_ids: list[str] = []

    for row in rows:
        if not row.dedup_key:
            skipped_ids.append(row.id)
            continue
        # Create fingerprint suppression rule
        rule = SuppressionRuleRow(
            id=str(uuid4()),
            pattern_type="fingerprint",
            pattern=row.dedup_key,
            reason=body.reason,
            created_by=body.created_by,
        )
        db.add(rule)
        row.status = "suppressed"
        suppressed_ids.append(row.id)

    await db.flush()
    return {
        "suppressed": len(suppressed_ids),
        "suppressed_ids": suppressed_ids,
        "skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
    }


@router.post("/bulk-dismiss", status_code=200)
async def bulk_dismiss(body: BulkDismissRequest, db: AsyncSession = Depends(get_db)):
    """Mark a list of findings as dismissed."""
    rows = await _fetch_findings(body.finding_ids, db)
    if not rows:
        raise HTTPException(status_code=404, detail="No findings found for given IDs")

    dismissed_ids: list[str] = []
    for row in rows:
        row.status = "dismissed"
        dismissed_ids.append(row.id)

    await db.flush()
    return {"dismissed": len(dismissed_ids), "dismissed_ids": dismissed_ids}


@router.post("/bulk-assign", status_code=200)
async def bulk_assign(body: BulkAssignRequest, db: AsyncSession = Depends(get_db)):
    """
    Assign a list of findings to a user.
    Stored in the finding's location JSONB as {"assignee": "..."} extension,
    or in explanation prefix until a dedicated column is added.
    Uses a lightweight annotation approach: sets `reachability` field as
    "assigned:<assignee>" so no schema change is required this phase.
    """
    rows = await _fetch_findings(body.finding_ids, db)
    if not rows:
        raise HTTPException(status_code=404, detail="No findings found for given IDs")

    assigned_ids: list[str] = []
    for row in rows:
        # Store assignment in location JSONB under "assignee" key
        loc = dict(row.location or {})
        loc["assignee"] = body.assignee
        row.location = loc
        assigned_ids.append(row.id)

    await db.flush()
    return {
        "assigned": len(assigned_ids),
        "assigned_ids": assigned_ids,
        "assignee": body.assignee,
    }
