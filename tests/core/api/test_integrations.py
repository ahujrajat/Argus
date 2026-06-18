# tests/core/api/test_integrations.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from core.api.app import create_app
from core.api.deps import get_db
from core.integrations.jira import IntegrationNotConfiguredError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding_row(
    finding_id: str | None = None,
    scan_id: str | None = None,
    rule_id: str = "sql-injection",
    severity: str = "high",
    source_tool: str = "semgrep",
    explanation: str | None = "Possible SQL injection.",
) -> MagicMock:
    row = MagicMock()
    row.id = finding_id or str(uuid4())
    row.scan_id = scan_id or str(uuid4())
    row.rule_id = rule_id
    row.severity = severity
    row.source_tool = source_tool
    row.explanation = explanation
    row.location = {"path": "app/login.py", "line": 42}
    return row


def _make_scan_row(
    scan_id: str | None = None,
    target_ref: str = "github.com/org/repo",
    status: str = "completed",
) -> MagicMock:
    row = MagicMock()
    row.id = scan_id or str(uuid4())
    row.target_ref = target_ref
    row.status = status
    return row


def _make_mock_db(scalar_result=None) -> AsyncMock:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


def _db_override(row):
    mock_db = _make_mock_db(scalar_result=row)

    async def override():
        yield mock_db

    return override


# ---------------------------------------------------------------------------
# Jira tests
# ---------------------------------------------------------------------------

async def test_create_jira_issue_success():
    app = create_app()
    finding = _make_finding_row()

    app.dependency_overrides[get_db] = _db_override(finding)
    try:
        with patch("core.api.routers.integrations.create_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {
                "issue_key": "PROJ-99",
                "url": "https://myorg.atlassian.net/browse/PROJ-99",
            }
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/integrations/jira/issue",
                    json={"finding_id": finding.id, "priority": "High"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert data["issue_key"] == "PROJ-99"
    assert "url" in data


async def test_create_jira_issue_not_configured_returns_503():
    app = create_app()
    finding = _make_finding_row()

    app.dependency_overrides[get_db] = _db_override(finding)
    try:
        with patch(
            "core.api.routers.integrations.create_issue",
            new_callable=AsyncMock,
            side_effect=IntegrationNotConfiguredError("JIRA_URL is not set"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/integrations/jira/issue",
                    json={"finding_id": finding.id},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


async def test_create_jira_issue_finding_not_found_returns_404():
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(None)  # no row
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/integrations/jira/issue",
                json={"finding_id": str(uuid4())},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PagerDuty tests
# ---------------------------------------------------------------------------

async def test_trigger_pagerduty_success():
    app = create_app()
    scan = _make_scan_row()

    app.dependency_overrides[get_db] = _db_override(scan)
    try:
        with patch("core.api.routers.integrations.trigger_incident", new_callable=AsyncMock) as mock_pd:
            mock_pd.return_value = {"status": "success", "dedup_key": "argus-scan-abc"}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/integrations/pagerduty/trigger",
                    json={"scan_id": scan.id, "severity": "error"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "dedup_key" in data


async def test_trigger_pagerduty_not_configured_returns_503():
    app = create_app()
    scan = _make_scan_row()

    app.dependency_overrides[get_db] = _db_override(scan)
    try:
        with patch(
            "core.api.routers.integrations.trigger_incident",
            new_callable=AsyncMock,
            side_effect=IntegrationNotConfiguredError("PD_ROUTING_KEY is not set"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/integrations/pagerduty/trigger",
                    json={"scan_id": scan.id},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


async def test_trigger_pagerduty_scan_not_found_returns_404():
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(None)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/integrations/pagerduty/trigger",
                json={"scan_id": str(uuid4())},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Slack tests
# ---------------------------------------------------------------------------

async def test_post_slack_finding_success(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    app = create_app()
    finding = _make_finding_row()

    app.dependency_overrides[get_db] = _db_override(finding)
    try:
        with patch("core.api.routers.integrations.post_rich_finding", new_callable=AsyncMock) as mock_slack:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/v1/integrations/slack/finding",
                    json={"finding_id": finding.id},
                )
            mock_slack.assert_called_once()
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


async def test_post_slack_finding_not_configured_returns_skipped(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    app = create_app()
    finding = _make_finding_row()

    app.dependency_overrides[get_db] = _db_override(finding)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/integrations/slack/finding",
                json={"finding_id": finding.id},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped"
    assert data["reason"] == "not_configured"


async def test_post_slack_finding_not_found_returns_404():
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(None)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/integrations/slack/finding",
                json={"finding_id": str(uuid4())},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
