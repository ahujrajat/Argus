# core/api/routers/integrations.py
"""Integrations hub — Jira, PagerDuty, and Slack endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import FindingRow, ScanRow
from core.integrations.jira import create_issue, IntegrationNotConfiguredError
from core.integrations.pagerduty import trigger_incident
from core.integrations.slack_rich import post_rich_finding

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class JiraIssueRequest(BaseModel):
    finding_id: str
    summary: str | None = None
    priority: str = "High"


class PagerDutyTriggerRequest(BaseModel):
    scan_id: str
    summary: str | None = None
    severity: str = "error"


class SlackFindingRequest(BaseModel):
    finding_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_finding(finding_id: str, db: AsyncSession) -> FindingRow:
    result = await db.execute(
        select(FindingRow).where(FindingRow.id == finding_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return row


async def _get_scan(scan_id: str, db: AsyncSession) -> ScanRow:
    result = await db.execute(select(ScanRow).where(ScanRow.id == scan_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/jira/issue", status_code=201)
async def create_jira_issue(
    body: JiraIssueRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a Jira issue from a finding."""
    finding = await _get_finding(body.finding_id, db)

    location = finding.location or {}
    file_path = location.get("path", "unknown")
    line = location.get("line", "?")

    summary = body.summary or f"[Argus] {finding.rule_id} — {finding.severity.upper()} in {file_path}"
    description = (
        f"Security finding detected by Argus.\n\n"
        f"Rule: {finding.rule_id}\n"
        f"Severity: {finding.severity}\n"
        f"Source tool: {finding.source_tool}\n"
        f"Location: {file_path}:{line}\n"
        f"Finding ID: {finding.id}\n"
    )
    if finding.explanation:
        description += f"\nExplanation:\n{finding.explanation}\n"

    try:
        result = await create_issue(
            summary=summary,
            description=description,
            priority=body.priority,
        )
    except IntegrationNotConfiguredError:
        raise HTTPException(status_code=503, detail="Jira integration not configured")

    return result


@router.post("/pagerduty/trigger", status_code=200)
async def trigger_pagerduty_incident(
    body: PagerDutyTriggerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a PagerDuty incident from a scan."""
    scan = await _get_scan(body.scan_id, db)

    summary = body.summary or (
        f"[Argus] Scan completed on {scan.target_ref} — review required"
    )

    try:
        result = await trigger_incident(
            summary=summary,
            severity=body.severity,
            source=scan.target_ref,
            dedup_key=f"argus-scan-{scan.id}",
            details={"scan_id": scan.id, "target_ref": scan.target_ref, "status": scan.status},
        )
    except IntegrationNotConfiguredError:
        raise HTTPException(status_code=503, detail="PagerDuty integration not configured")

    return result


@router.post("/slack/finding", status_code=200)
async def post_slack_finding(
    body: SlackFindingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Post a rich Slack notification for a finding."""
    finding = await _get_finding(body.finding_id, db)

    import os
    if not os.environ.get("SLACK_WEBHOOK_URL", ""):
        return {"status": "skipped", "reason": "not_configured"}

    location = finding.location or {}
    file_path = location.get("path", "unknown")
    line = location.get("line", 0)

    await post_rich_finding(
        scan_id=finding.scan_id,
        target_ref="",
        rule_id=finding.rule_id,
        severity=finding.severity,
        file=file_path,
        line=line,
        explanation=finding.explanation,
    )
    return {"status": "sent"}
