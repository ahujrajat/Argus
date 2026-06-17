# core/api/routers/scans.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.tables import ScanRow, FindingRow
from core.model.entities import ScanMode

router = APIRouter(prefix="/scans", tags=["scans"])


class TriggerScanRequest(BaseModel):
    target_ref: str
    mode: ScanMode = ScanMode.at_rest
    pipeline_config_name: str = "full-scan"


@router.get("/")
async def list_scans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).order_by(ScanRow.started_at.desc()).limit(50))
    rows = result.scalars().all()
    return [{"id": r.id, "target_ref": r.target_ref, "status": r.status,
             "mode": r.mode, "cost_usd": r.cost_usd} for r in rows]


@router.post("/", status_code=202)
async def trigger_scan(
    body: TriggerScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from uuid import uuid4
    from core.model.entities import Scan
    from core.db.tables import ScanRow as SR
    from datetime import datetime, timezone
    import os

    scan_id = uuid4()
    row = SR(
        id=str(scan_id),
        target_ref=body.target_ref,
        pipeline_config_id=str(uuid4()),
        mode=body.mode.value,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    scan = Scan(id=scan_id, target_ref=body.target_ref,
                pipeline_config_id=scan_id, mode=body.mode)

    from core.governance.gate import GovernanceGate
    from core.agents.orchestrator import Orchestrator

    config_path = f"config/pipeline_configs/{body.pipeline_config_name}.yaml"
    gate = GovernanceGate()
    orch = Orchestrator(gate=gate, pipeline_config_path=config_path)

    async def _run():
        from core.db.session import get_session
        async with get_session() as s:
            await orch.run(scan, s)

    background_tasks.add_task(_run)
    return {"scan_id": str(scan_id), "status": "accepted"}


@router.get("/{scan_id}")
async def get_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"id": row.id, "target_ref": row.target_ref, "status": row.status,
            "mode": row.mode, "cost_usd": row.cost_usd,
            "started_at": row.started_at, "finished_at": row.finished_at}
