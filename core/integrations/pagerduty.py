# core/integrations/pagerduty.py
"""PagerDuty integration — triggers incidents via the Events v2 API."""
from __future__ import annotations
import os
import uuid
import structlog
import httpx

from core.integrations.jira import IntegrationNotConfiguredError

log = structlog.get_logger()

_PD_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


async def trigger_incident(
    summary: str,
    severity: str,
    source: str,
    dedup_key: str | None = None,
    details: dict | None = None,
) -> dict:
    """Trigger a PagerDuty incident and return {"status": ..., "dedup_key": ...}.

    Reads environment variable:
    - PD_ROUTING_KEY    PagerDuty Events v2 integration routing key
    """
    routing_key = os.environ.get("PD_ROUTING_KEY", "")
    if not routing_key:
        raise IntegrationNotConfiguredError("PD_ROUTING_KEY is not set")

    resolved_dedup_key = dedup_key or str(uuid.uuid4())

    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": resolved_dedup_key,
        "payload": {
            "summary": summary,
            "severity": severity,
            "source": source,
            "custom_details": details or {},
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_PD_EVENTS_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status", "success")
    log.info("pagerduty_incident_triggered", dedup_key=resolved_dedup_key, status=status)
    return {"status": status, "dedup_key": resolved_dedup_key}
