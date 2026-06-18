# tests/core/integrations/test_slack_rich.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from core.integrations.slack_rich import post_rich_finding, post_rich_scan_summary


def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_post_rich_finding_sends_blocks(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

    mock_resp = _mock_response(200)
    captured = {}

    async def fake_post(url, json=None):
        captured["url"] = url
        captured["body"] = json
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await post_rich_finding(
            scan_id="scan-abc",
            target_ref="github.com/org/repo",
            rule_id="sql-injection",
            severity="critical",
            file="app/login.py",
            line=42,
            explanation="Unsanitized user input in SQL query.",
        )

    assert "blocks" in captured["body"]
    blocks = captured["body"]["blocks"]
    # Header block present
    header = blocks[0]
    assert header["type"] == "header"
    assert "Security Finding" in header["text"]["text"]
    # Section with fields present
    section = blocks[1]
    assert section["type"] == "section"
    field_texts = [f["text"] for f in section["fields"]]
    assert any("sql-injection" in t for t in field_texts)
    assert any("CRITICAL" in t for t in field_texts)
    assert any("app/login.py:42" in t for t in field_texts)


async def test_post_rich_finding_no_op_when_no_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    with patch("httpx.AsyncClient") as mock_client_cls:
        await post_rich_finding(
            scan_id="s1",
            target_ref="repo",
            rule_id="xss",
            severity="high",
            file="app.py",
            line=1,
        )
        mock_client_cls.assert_not_called()


async def test_post_rich_finding_swallows_http_error(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

    mock_resp = _mock_response(500)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        # Should not raise
        await post_rich_finding(
            scan_id="s1",
            target_ref="repo",
            rule_id="xss",
            severity="high",
            file="app.py",
            line=1,
        )


async def test_post_rich_scan_summary_sends_blocks(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

    mock_resp = _mock_response(200)
    captured = {}

    async def fake_post(url, json=None):
        captured["body"] = json
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await post_rich_scan_summary(
            scan_id="scan-xyz",
            target_ref="github.com/org/repo",
            total=15,
            critical=2,
            high=5,
            risk_score=42.5,
        )

    blocks = captured["body"]["blocks"]
    header = blocks[0]
    assert header["type"] == "header"
    assert "Scan Complete" in header["text"]["text"]

    section = blocks[1]
    field_texts = [f["text"] for f in section["fields"]]
    assert any("15" in t for t in field_texts)
    assert any("42.5" in t for t in field_texts)


async def test_post_rich_scan_summary_no_op_when_no_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    with patch("httpx.AsyncClient") as mock_client_cls:
        await post_rich_scan_summary(
            scan_id="s1",
            target_ref="repo",
            total=0,
            critical=0,
            high=0,
            risk_score=0.0,
        )
        mock_client_cls.assert_not_called()
