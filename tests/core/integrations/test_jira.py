# tests/core/integrations/test_jira.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from core.integrations.jira import create_issue, IntegrationNotConfiguredError


def _mock_response(status_code: int = 201, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {"key": "PROJ-123", "id": "10001"}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_create_issue_success(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://myorg.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok123")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")

    mock_resp = _mock_response(201, {"key": "PROJ-456"})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await create_issue(
            summary="SQL Injection in login",
            description="Found SQL injection at /login endpoint.",
        )

    assert result["issue_key"] == "PROJ-456"
    assert result["url"] == "https://myorg.atlassian.net/browse/PROJ-456"


async def test_create_issue_missing_jira_url_raises(monkeypatch):
    monkeypatch.delenv("JIRA_URL", raising=False)

    with pytest.raises(IntegrationNotConfiguredError, match="JIRA_URL"):
        await create_issue(summary="test", description="desc")


async def test_create_issue_with_labels(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://myorg.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    monkeypatch.setenv("JIRA_EMAIL", "u@e.com")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SEC")

    mock_resp = _mock_response(201, {"key": "SEC-1"})

    captured_payload = {}

    async def fake_post(url, json=None, headers=None):
        captured_payload.update(json or {})
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        result = await create_issue(
            summary="XSS",
            description="cross-site scripting",
            labels=["security", "argus"],
        )

    assert result["issue_key"] == "SEC-1"
    assert "labels" in captured_payload["fields"]
    assert captured_payload["fields"]["labels"] == ["security", "argus"]


async def test_create_issue_http_error_propagates(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://myorg.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "bad_token")
    monkeypatch.setenv("JIRA_EMAIL", "u@e.com")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")

    mock_resp = _mock_response(401)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await create_issue(summary="test", description="desc")
