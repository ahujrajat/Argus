# core/api/routers/scans.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.tables import ScanRow, FindingRow
from core.model.entities import ScanMode, SecurityApproach

router = APIRouter(prefix="/scans", tags=["scans"])


class TriggerScanRequest(BaseModel):
    target_ref: str
    mode: ScanMode = ScanMode.at_rest
    approach: SecurityApproach = SecurityApproach.penetration_testing
    pipeline_config_name: str = "full-scan"


class BatchScanRequest(BaseModel):
    scans: list[TriggerScanRequest]


@router.get("/")
async def list_scans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).order_by(ScanRow.started_at.desc()).limit(50))
    rows = result.scalars().all()
    return [{"id": r.id, "target_ref": r.target_ref, "status": r.status,
             "mode": r.mode, "approach": r.approach, "cost_usd": r.cost_usd} for r in rows]


@router.post("/", status_code=202)
async def trigger_scan(
    body: TriggerScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from uuid import uuid4, UUID as _UUID
    from core.model.entities import Scan
    from core.db.tables import ScanRow as SR, PipelineConfigRow
    from datetime import datetime, timezone

    # Resolve the pipeline config from DB to get its real ID
    pc_result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.name == body.pipeline_config_name)
    )
    pc_row = pc_result.scalar_one_or_none()
    if pc_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline config '{body.pipeline_config_name}' not found",
        )

    scan_id = uuid4()
    row = SR(
        id=str(scan_id),
        target_ref=body.target_ref,
        pipeline_config_id=str(pc_row.id),
        mode=body.mode.value,
        approach=body.approach.value,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    scan = Scan(
        id=scan_id,
        target_ref=body.target_ref,
        pipeline_config_id=_UUID(str(pc_row.id)),
        mode=body.mode,
        approach=body.approach,
    )

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


@router.post("/batch", status_code=202)
async def trigger_scan_batch(
    body: BatchScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from uuid import uuid4, UUID as _UUID
    from core.model.entities import Scan
    from core.db.tables import ScanRow as SR, PipelineConfigRow
    from datetime import datetime, timezone

    if not body.scans:
        raise HTTPException(status_code=422, detail="scans list must not be empty")

    # Validate all pipeline configs upfront before inserting anything
    pipeline_rows: dict[str, object] = {}
    for item in body.scans:
        if item.pipeline_config_name not in pipeline_rows:
            pc_result = await db.execute(
                select(PipelineConfigRow).where(PipelineConfigRow.name == item.pipeline_config_name)
            )
            pc_row = pc_result.scalar_one_or_none()
            if pc_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline config '{item.pipeline_config_name}' not found",
                )
            pipeline_rows[item.pipeline_config_name] = pc_row

    from core.governance.gate import GovernanceGate
    from core.agents.orchestrator import Orchestrator

    scan_ids: list[str] = []
    for item in body.scans:
        pc_row = pipeline_rows[item.pipeline_config_name]
        scan_id = uuid4()
        row = SR(
            id=str(scan_id),
            target_ref=item.target_ref,
            pipeline_config_id=str(pc_row.id),
            mode=item.mode.value,
            approach=item.approach.value,
            status="pending",
            started_at=datetime.now(timezone.utc),
        )
        db.add(row)

        scan = Scan(
            id=scan_id,
            target_ref=item.target_ref,
            pipeline_config_id=_UUID(str(pc_row.id)),
            mode=item.mode,
            approach=item.approach,
        )

        config_path = f"config/pipeline_configs/{item.pipeline_config_name}.yaml"
        gate = GovernanceGate()
        orch = Orchestrator(gate=gate, pipeline_config_path=config_path)

        async def _run(s=scan, o=orch):
            from core.db.session import get_session
            async with get_session() as sess:
                await o.run(s, sess)

        background_tasks.add_task(_run)
        scan_ids.append(str(scan_id))

    await db.flush()
    return {"batch_id": str(uuid4()), "scan_ids": scan_ids, "status": "accepted"}


@router.get("/{scan_id}")
async def get_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"id": row.id, "target_ref": row.target_ref, "status": row.status,
            "mode": row.mode, "approach": row.approach, "cost_usd": row.cost_usd,
            "started_at": row.started_at, "finished_at": row.finished_at}


@router.get("/{scan_id}/sbom")
async def get_scan_sbom(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    from core.sbom.cyclonedx import build_sbom

    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")

    findings_result = await db.execute(
        select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    )
    findings = findings_result.scalars().all()
    findings_dicts = [
        {
            "rule_id": f.rule_id,
            "source_tool": f.source_tool,
            "cwe": f.cwe,
            "owasp_category": f.owasp_category,
            "severity": f.severity,
            "location": f.location,
            "dedup_key": f.dedup_key,
            "explanation": f.explanation,
        }
        for f in findings
    ]

    sbom = build_sbom(
        scan_id=str(scan_id),
        target_ref=row.target_ref,
        findings=findings_dicts,
    )
    return sbom


@router.get("/{scan_id}/compare/{baseline_scan_id}")
async def compare_scans(
    scan_id: UUID,
    baseline_scan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    from core.analysis.scan_diff import diff_scans

    async def _fetch(sid: str) -> list[dict]:
        r = await db.execute(select(FindingRow).where(FindingRow.scan_id == sid))
        rows = r.scalars().all()
        return [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "source_tool": f.source_tool,
                "severity": f.severity,
                "dedup_key": f.dedup_key,
                "location": f.location,
                "explanation": f.explanation,
            }
            for f in rows
        ]

    for sid, label in [(str(scan_id), "scan_id"), (str(baseline_scan_id), "baseline_scan_id")]:
        r = await db.execute(select(ScanRow).where(ScanRow.id == sid))
        if not r.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"{label} not found")

    baseline_findings = await _fetch(str(baseline_scan_id))
    current_findings = await _fetch(str(scan_id))

    result = diff_scans(baseline=baseline_findings, current=current_findings)
    return {
        "scan_id": str(scan_id),
        "baseline_scan_id": str(baseline_scan_id),
        "summary": result.summary(),
        "new": result.new_findings,
        "persisted": result.persisted_findings,
        "resolved": result.resolved_findings,
    }


@router.get("/{scan_id}/report")
async def compliance_report(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    """OWASP Top 10 + CWE + severity breakdown compliance report."""
    from collections import Counter

    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")

    findings_result = await db.execute(
        select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    )
    findings = findings_result.scalars().all()

    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "negligible": 0}
    severity_counts: Counter = Counter()
    owasp_counts: Counter = Counter()
    cwe_counts: Counter = Counter()

    for f in findings:
        severity_counts[f.severity.lower()] += 1
        if f.owasp_category:
            owasp_counts[f.owasp_category] += 1
        if f.cwe:
            cwe_counts[f.cwe] += 1

    # Risk score: weighted sum (critical=10, high=5, medium=2, low=1)
    weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
    risk_score = sum(weights.get(sev, 0) * cnt for sev, cnt in severity_counts.items())

    return {
        "scan_id": str(scan_id),
        "target_ref": row.target_ref,
        "status": row.status,
        "total_findings": len(findings),
        "risk_score": risk_score,
        "severity_breakdown": dict(severity_counts),
        "owasp_top10": dict(owasp_counts.most_common(10)),
        "cwe_top10": dict(cwe_counts.most_common(10)),
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }


@router.delete("/{scan_id}", status_code=200)
async def cancel_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone

    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    if row.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Scan is already {row.status} and cannot be cancelled",
        )
    row.status = "cancelled"
    row.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return {"scan_id": str(scan_id), "status": "cancelled"}
