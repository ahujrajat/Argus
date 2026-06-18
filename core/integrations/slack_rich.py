# core/integrations/slack_rich.py
"""Slack rich Block Kit notifications for findings and scan summaries."""
from __future__ import annotations
import os
import structlog
import httpx

log = structlog.get_logger()


def _webhook_url() -> str:
    return os.environ.get("SLACK_WEBHOOK_URL", "")


async def _post_blocks(blocks: list[dict]) -> None:
    """Fire-and-forget POST to Slack webhook. Swallows all errors."""
    url = _webhook_url()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"blocks": blocks})
            resp.raise_for_status()
    except Exception as exc:
        log.warning("slack_rich_post_failed", error=str(exc))


async def post_rich_finding(
    scan_id: str,
    target_ref: str,
    rule_id: str,
    severity: str,
    file: str,
    line: int | str,
    explanation: str | None = None,
) -> None:
    """Post a rich Slack Block Kit message for an individual finding."""
    if not _webhook_url():
        return

    severity_upper = severity.upper()
    emoji = ":rotating_light:" if severity_upper in ("CRITICAL", "HIGH") else ":warning:"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Security Finding Detected",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Rule:*\n`{rule_id}`"},
                {"type": "mrkdwn", "text": f"*Severity:*\n*{severity_upper}*"},
                {"type": "mrkdwn", "text": f"*File:*\n`{file}:{line}`"},
                {"type": "mrkdwn", "text": f"*Target:*\n`{target_ref}`"},
            ],
        },
    ]

    if explanation:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Explanation:*\n{explanation}"},
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Scan ID: `{scan_id}`  |  Argus Security Platform"}
            ],
        }
    )

    await _post_blocks(blocks)


async def post_rich_scan_summary(
    scan_id: str,
    target_ref: str,
    total: int,
    critical: int,
    high: int,
    risk_score: float,
) -> None:
    """Post a rich Slack Block Kit message summarising a completed scan."""
    if not _webhook_url():
        return

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":white_check_mark: Scan Complete",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Target:*\n`{target_ref}`"},
                {"type": "mrkdwn", "text": f"*Total Findings:*\n{total}"},
                {"type": "mrkdwn", "text": f"*Critical:*\n{critical}"},
                {"type": "mrkdwn", "text": f"*High:*\n{high}"},
                {"type": "mrkdwn", "text": f"*Risk Score:*\n{risk_score}"},
            ],
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Scan ID: `{scan_id}`  |  Argus Security Platform"}
            ],
        },
    ]

    await _post_blocks(blocks)
