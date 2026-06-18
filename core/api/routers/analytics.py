# core/api/routers/analytics.py
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import get_db
from core.analytics.trends import compute_finding_trend, compute_mttr, top_rules
from core.db.tables import FindingRow, ScanRow

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _recent_scans(db: AsyncSession, days_back: int) -> list[ScanRow]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    result = await db.execute(
        select(ScanRow).where(ScanRow.started_at >= cutoff)
    )
    return list(result.scalars().all())


async def _findings_for_scans(db: AsyncSession, scan_ids: list[str]) -> list[FindingRow]:
    if not scan_ids:
        return []
    result = await db.execute(
        select(FindingRow).where(FindingRow.scan_id.in_(scan_ids))
    )
    return list(result.scalars().all())


@router.get("/trends")
async def trends_endpoint(
    granularity: Literal["day", "week"] = "day",
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())
    findings = await _findings_for_scans(db, scan_ids)

    finding_dicts = [
        {
            "created_at": scan_map[f.scan_id].started_at or datetime.now(timezone.utc),
            "severity": f.severity,
        }
        for f in findings
        if f.scan_id in scan_map
    ]
    return compute_finding_trend(finding_dicts, granularity=granularity, days_back=days_back)


@router.get("/mttr")
async def mttr_endpoint(
    days_back: int = 90,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())

    if not scan_ids:
        return compute_mttr([])

    result = await db.execute(
        select(FindingRow).where(
            FindingRow.scan_id.in_(scan_ids),
            FindingRow.status == "fixed",
        )
    )
    findings = list(result.scalars().all())

    finding_dicts = [
        {
            "created_at": scan_map[f.scan_id].started_at or datetime.now(timezone.utc),
            "resolved_at": scan_map[f.scan_id].finished_at,
        }
        for f in findings
        if f.scan_id in scan_map
    ]
    return compute_mttr(finding_dicts)


@router.get("/top-rules")
async def top_rules_endpoint(
    top_n: int = 10,
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_ids = [s.id for s in scans]
    findings = await _findings_for_scans(db, scan_ids)

    finding_dicts = [{"rule_id": f.rule_id} for f in findings]
    return top_rules(finding_dicts, top_n=top_n)


@router.get("/summary")
async def summary_endpoint(
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_ids = [s.id for s in scans]
    findings = await _findings_for_scans(db, scan_ids)

    severity_counts: Counter = Counter()
    owasp_counts: Counter = Counter()
    for f in findings:
        severity_counts[f.severity.lower()] += 1
        if f.owasp_category:
            owasp_counts[f.owasp_category] += 1

    risk_weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
    avg_risk = (
        sum(
            risk_weights.get(sev, 0) * cnt
            for sev, cnt in severity_counts.items()
        ) / max(len(findings), 1)
    )

    return {
        "total_scans": len(scans),
        "total_findings": len(findings),
        "severity_breakdown": dict(severity_counts),
        "top_owasp_categories": dict(owasp_counts.most_common(5)),
        "average_risk_score": round(avg_risk, 2),
        "days_back": days_back,
    }
