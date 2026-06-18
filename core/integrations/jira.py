# core/integrations/jira.py
"""Jira integration — creates issues via the Jira REST API v3."""
from __future__ import annotations
import os
import base64
import structlog
import httpx

log = structlog.get_logger()


class IntegrationNotConfiguredError(Exception):
    """Raised when a required integration env var is missing."""


async def create_issue(
    summary: str,
    description: str,
    issue_type: str = "Bug",
    priority: str = "High",
    labels: list[str] | None = None,
) -> dict:
    """Create a Jira issue and return {"issue_key": ..., "url": ...}.

    Reads environment variables:
    - JIRA_URL           Base URL, e.g. https://myorg.atlassian.net
    - JIRA_API_TOKEN     Personal API token
    - JIRA_EMAIL         Atlassian account e-mail
    - JIRA_PROJECT_KEY   Jira project key, e.g. PROJ
    """
    jira_url = os.environ.get("JIRA_URL", "")
    api_token = os.environ.get("JIRA_API_TOKEN", "")
    email = os.environ.get("JIRA_EMAIL", "")
    project_key = os.environ.get("JIRA_PROJECT_KEY", "")

    if not jira_url:
        raise IntegrationNotConfiguredError("JIRA_URL is not set")

    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload: dict = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }
    if labels:
        payload["fields"]["labels"] = labels

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{jira_url}/rest/api/3/issue",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    issue_key = data["key"]
    issue_url = f"{jira_url}/browse/{issue_key}"
    log.info("jira_issue_created", issue_key=issue_key)
    return {"issue_key": issue_key, "url": issue_url}
