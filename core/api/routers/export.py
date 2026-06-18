# core/api/routers/export.py
from __future__ import annotations
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import get_db
from core.db.tables import FindingRow, ScanRow

router = APIRouter(prefix="/scans", tags=["export"])

_CSV_COLUMNS = [
    "scan_id", "target_ref", "rule_id", "severity",
    "owasp_category", "cwe", "file", "line", "status", "dedup_key",
]


@router.get("/export/csv")
async def export_findings_csv(
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    scan_result = await db.execute(
        select(ScanRow).where(ScanRow.started_at >= cutoff)
    )
    scans = list(scan_result.scalars().all())
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())

    findings: list[FindingRow] = []
    if scan_ids:
        finding_result = await db.execute(
            select(FindingRow).where(FindingRow.scan_id.in_(scan_ids))
        )
        findings = list(finding_result.scalars().all())

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()

        for f in findings:
            scan = scan_map.get(f.scan_id)
            location = f.location or {}
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
            writer.writerow({
                "scan_id": f.scan_id,
                "target_ref": scan.target_ref if scan else "",
                "rule_id": f.rule_id,
                "severity": f.severity,
                "owasp_category": f.owasp_category or "",
                "cwe": f.cwe or "",
                "file": location.get("file", ""),
                "line": location.get("line", ""),
                "status": f.status,
                "dedup_key": f.dedup_key,
            })
            yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=findings.csv"},
    )
