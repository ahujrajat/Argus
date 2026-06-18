# core/notifications/dispatcher.py
from __future__ import annotations
import os
import asyncio
import structlog
import httpx
from dataclasses import dataclass
from enum import Enum

log = structlog.get_logger()

_SLACK_WEBHOOK_URL = os.environ.get("ARGUS_SLACK_WEBHOOK_URL", "")
_NOTIFY_WEBHOOK_URL = os.environ.get("ARGUS_NOTIFY_WEBHOOK_URL", "")
_NOTIFY_MIN_SEVERITY = os.environ.get("ARGUS_NOTIFY_MIN_SEVERITY", "high")

_SEVERITY_RANK = {"info": 0, "informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class NotificationEvent(str, Enum):
    scan_completed = "scan_completed"
    high_severity_finding = "high_severity_finding"
    budget_warning = "budget_warning"
    budget_exceeded = "budget_exceeded"
    dast_unauthorized = "dast_unauthorized"


@dataclass
class Notification:
    event: NotificationEvent
    scan_id: str
    target_ref: str
    payload: dict


def _severity_meets_threshold(severity: str) -> bool:
    return _SEVERITY_RANK.get(severity.lower(), 0) >= _SEVERITY_RANK.get(_NOTIFY_MIN_SEVERITY, 3)


def _slack_blocks(n: Notification) -> list[dict]:
    icon = {
        NotificationEvent.scan_completed: ":white_check_mark:",
        NotificationEvent.high_severity_finding: ":rotating_light:",
        NotificationEvent.budget_warning: ":warning:",
        NotificationEvent.budget_exceeded: ":no_entry:",
        NotificationEvent.dast_unauthorized: ":lock:",
    }.get(n.event, ":bell:")

    title = {
        NotificationEvent.scan_completed: "Scan completed",
        NotificationEvent.high_severity_finding: "High-severity finding detected",
        NotificationEvent.budget_warning: "Budget warning",
        NotificationEvent.budget_exceeded: "Budget exceeded — scan stopped",
        NotificationEvent.dast_unauthorized: "DAST scan blocked (no authorization)",
    }.get(n.event, n.event.value)

    lines = [f"{icon} *{title}*", f"Scan: `{n.scan_id}`", f"Target: `{n.target_ref}`"]

    p = n.payload
    if n.event == NotificationEvent.scan_completed:
        lines.append(f"Findings: {p.get('finding_count', 0)}  |  Cost: ${p.get('cost_usd', 0):.4f}")
    elif n.event == NotificationEvent.high_severity_finding:
        lines.append(
            f"Rule: `{p.get('rule_id', '?')}`  |  Severity: *{p.get('severity', '?').upper()}*"
        )
        lines.append(f"File: `{p.get('file', '?')}:{p.get('line', '?')}`")
    elif n.event in (NotificationEvent.budget_warning, NotificationEvent.budget_exceeded):
        lines.append(f"Used: ${p.get('used_usd', 0):.4f} / ${p.get('limit_usd', 0):.4f}")

    return [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]


async def _post(url: str, body: dict, label: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            log.info("notification_sent", channel=label)
    except Exception as exc:
        log.warning("notification_failed", channel=label, error=str(exc))


async def dispatch(n: Notification) -> None:
    tasks = []

    if _SLACK_WEBHOOK_URL:
        body = {"blocks": _slack_blocks(n)}
        tasks.append(_post(_SLACK_WEBHOOK_URL, body, "slack"))

    if _NOTIFY_WEBHOOK_URL:
        body = {
            "event": n.event.value,
            "scan_id": n.scan_id,
            "target_ref": n.target_ref,
            **n.payload,
        }
        tasks.append(_post(_NOTIFY_WEBHOOK_URL, body, "webhook"))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def notify_scan_completed(
    scan_id: str,
    target_ref: str,
    finding_count: int,
    cost_usd: float,
) -> None:
    await dispatch(Notification(
        event=NotificationEvent.scan_completed,
        scan_id=scan_id,
        target_ref=target_ref,
        payload={"finding_count": finding_count, "cost_usd": cost_usd},
    ))


async def notify_high_severity_finding(
    scan_id: str,
    target_ref: str,
    rule_id: str,
    severity: str,
    file: str,
    line: int,
) -> None:
    if not _severity_meets_threshold(severity):
        return
    await dispatch(Notification(
        event=NotificationEvent.high_severity_finding,
        scan_id=scan_id,
        target_ref=target_ref,
        payload={"rule_id": rule_id, "severity": severity, "file": file, "line": line},
    ))


async def notify_budget_warning(
    scan_id: str,
    target_ref: str,
    used_usd: float,
    limit_usd: float,
) -> None:
    await dispatch(Notification(
        event=NotificationEvent.budget_warning,
        scan_id=scan_id,
        target_ref=target_ref,
        payload={"used_usd": used_usd, "limit_usd": limit_usd},
    ))
