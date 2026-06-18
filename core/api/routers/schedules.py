# core/api/routers/schedules.py
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from croniter import croniter

from core.api.deps import get_db
from core.db.tables import ScheduledScanRow

router = APIRouter(prefix="/schedules", tags=["schedules"])


class CreateScheduleRequest(BaseModel):
    name: str
    cron_expr: str
    pipeline_config_name: str
    target_ref: str
    enabled: bool = True

    @field_validator("cron_expr")
    @classmethod
    def cron_must_be_valid(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: {v!r}")
        return v

    @field_validator("name", "pipeline_config_name", "target_ref")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty")
        return v


def _row_to_dict(r: ScheduledScanRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "cron_expr": r.cron_expr,
        "pipeline_config_name": r.pipeline_config_name,
        "target_ref": r.target_ref,
        "enabled": r.enabled,
        "last_run_at": r.last_run_at,
        "next_run_at": r.next_run_at,
        "created_at": r.created_at,
    }


def _compute_next_run(cron_expr: str) -> datetime:
    it = croniter(cron_expr, datetime.now(timezone.utc))
    return it.get_next(datetime)


@router.post("/", status_code=201)
async def create_schedule(
    body: CreateScheduleRequest,
    db: AsyncSession = Depends(get_db),
):
    row = ScheduledScanRow(
        id=str(uuid4()),
        name=body.name,
        cron_expr=body.cron_expr,
        pipeline_config_name=body.pipeline_config_name,
        target_ref=body.target_ref,
        enabled=body.enabled,
        next_run_at=_compute_next_run(body.cron_expr) if body.enabled else None,
    )
    db.add(row)
    await db.flush()
    return _row_to_dict(row)


@router.get("/")
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledScanRow).order_by(ScheduledScanRow.created_at.desc())
    )
    return [_row_to_dict(r) for r in result.scalars().all()]


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledScanRow).where(ScheduledScanRow.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _row_to_dict(row)


@router.patch("/{schedule_id}/enable", status_code=200)
async def enable_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledScanRow).where(ScheduledScanRow.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    row.enabled = True
    row.next_run_at = _compute_next_run(row.cron_expr)
    await db.flush()
    return _row_to_dict(row)


@router.patch("/{schedule_id}/disable", status_code=200)
async def disable_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledScanRow).where(ScheduledScanRow.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    row.enabled = False
    row.next_run_at = None
    await db.flush()
    return _row_to_dict(row)


@router.delete("/{schedule_id}", status_code=200)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledScanRow).where(ScheduledScanRow.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(row)
    await db.flush()
    return {"id": schedule_id, "status": "deleted"}
