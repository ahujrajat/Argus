# tests/core/integrations/test_pagerduty.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from core.integrations.pagerduty import trigger_incident
from core.integrations.jira import IntegrationNotConfiguredError


def _mock_response(status_code: int = 202, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {"status": "success", "message": "Event processed"}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_trigger_incident_success(monkeypatch):
    monkeypatch.setenv("PD_ROUTING_KEY", "rk_abc123")

    mock_resp = _mock_response(202, {"status": "success", "message": "Event processed"})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await trigger_incident(
            summary="Critical vulnerability found",
            severity="critical",
            source="github.com/myorg/myrepo",
            dedup_key="argus-scan-123",
        )

    assert result["status"] == "success"
    assert result["dedup_key"] == "argus-scan-123"


async def test_trigger_incident_generates_dedup_key(monkeypatch):
    monkeypatch.setenv("PD_ROUTING_KEY", "rk_abc123")

    mock_resp = _mock_response(202, {"status": "success"})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await trigger_incident(
            summary="High severity alert",
            severity="error",
            source="myapp",
        )

    assert result["dedup_key"]  # auto-generated UUID
    assert len(result["dedup_key"]) == 36  # UUID format


async def test_trigger_incident_missing_routing_key_raises(monkeypatch):
    monkeypatch.delenv("PD_ROUTING_KEY", raising=False)

    with pytest.raises(IntegrationNotConfiguredError, match="PD_ROUTING_KEY"):
        await trigger_incident(
            summary="test",
            severity="error",
            source="test",
        )


async def test_trigger_incident_http_error_propagates(monkeypatch):
    monkeypatch.setenv("PD_ROUTING_KEY", "bad_key")

    mock_resp = _mock_response(400)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await trigger_incident(
                summary="test",
                severity="error",
                source="test",
            )


async def test_trigger_incident_sends_correct_payload(monkeypatch):
    monkeypatch.setenv("PD_ROUTING_KEY", "rk_test")

    mock_resp = _mock_response(202, {"status": "success"})
    captured = {}

    async def fake_post(url, json=None):
        captured.update(json or {})
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await trigger_incident(
            summary="Alert",
            severity="warning",
            source="argus",
            dedup_key="my-key",
            details={"scan_id": "abc"},
        )

    assert captured["routing_key"] == "rk_test"
    assert captured["event_action"] == "trigger"
    assert captured["dedup_key"] == "my-key"
    assert captured["payload"]["summary"] == "Alert"
    assert captured["payload"]["severity"] == "warning"
    assert captured["payload"]["source"] == "argus"
    assert captured["payload"]["custom_details"] == {"scan_id": "abc"}
