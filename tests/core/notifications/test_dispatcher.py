# tests/core/notifications/test_dispatcher.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from core.notifications.dispatcher import (
    Notification, NotificationEvent, dispatch,
    notify_scan_completed, notify_high_severity_finding, notify_budget_warning,
    _severity_meets_threshold, _slack_blocks,
)


class TestSeverityThreshold:
    def test_critical_meets_high_threshold(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"):
            assert _severity_meets_threshold("critical")

    def test_high_meets_high_threshold(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"):
            assert _severity_meets_threshold("high")

    def test_medium_does_not_meet_high_threshold(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"):
            assert not _severity_meets_threshold("medium")

    def test_low_meets_low_threshold(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "low"):
            assert _severity_meets_threshold("low")

    def test_case_insensitive(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"):
            assert _severity_meets_threshold("CRITICAL")


class TestSlackBlocks:
    def test_scan_completed_block(self):
        n = Notification(
            event=NotificationEvent.scan_completed,
            scan_id="scan-123",
            target_ref="/repo/app",
            payload={"finding_count": 5, "cost_usd": 0.0123},
        )
        blocks = _slack_blocks(n)
        assert len(blocks) == 1
        text = blocks[0]["text"]["text"]
        assert "Scan completed" in text
        assert "scan-123" in text
        assert "Findings: 5" in text

    def test_high_severity_block(self):
        n = Notification(
            event=NotificationEvent.high_severity_finding,
            scan_id="scan-456",
            target_ref="/repo/app",
            payload={"rule_id": "sql-injection", "severity": "high", "file": "app.py", "line": 42},
        )
        blocks = _slack_blocks(n)
        text = blocks[0]["text"]["text"]
        assert "sql-injection" in text
        assert "HIGH" in text
        assert "app.py:42" in text

    def test_budget_warning_block(self):
        n = Notification(
            event=NotificationEvent.budget_warning,
            scan_id="scan-789",
            target_ref="/repo/app",
            payload={"used_usd": 4.0, "limit_usd": 5.0},
        )
        blocks = _slack_blocks(n)
        text = blocks[0]["text"]["text"]
        assert "Budget warning" in text
        assert "$4.0000" in text


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_skips_when_no_urls_configured(self):
        n = Notification(
            event=NotificationEvent.scan_completed,
            scan_id="s1",
            target_ref="/repo",
            payload={"finding_count": 0, "cost_usd": 0.0},
        )
        with patch("core.notifications.dispatcher._SLACK_WEBHOOK_URL", ""), \
             patch("core.notifications.dispatcher._NOTIFY_WEBHOOK_URL", ""):
            # Should complete without error and without HTTP calls
            await dispatch(n)

    @pytest.mark.asyncio
    async def test_dispatch_posts_to_slack(self):
        n = Notification(
            event=NotificationEvent.scan_completed,
            scan_id="s1",
            target_ref="/repo",
            payload={"finding_count": 3, "cost_usd": 0.05},
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("core.notifications.dispatcher._SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.notifications.dispatcher._NOTIFY_WEBHOOK_URL", ""), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            await dispatch(n)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/test"
        assert "blocks" in call_args[1]["json"]

    @pytest.mark.asyncio
    async def test_dispatch_does_not_raise_on_http_error(self):
        n = Notification(
            event=NotificationEvent.scan_completed,
            scan_id="s1",
            target_ref="/repo",
            payload={"finding_count": 0, "cost_usd": 0.0},
        )
        with patch("core.notifications.dispatcher._SLACK_WEBHOOK_URL", "https://bad-url"), \
             patch("core.notifications.dispatcher._NOTIFY_WEBHOOK_URL", ""), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            # Must not raise
            await dispatch(n)


class TestNotifyHelpers:
    @pytest.mark.asyncio
    async def test_notify_high_severity_skips_below_threshold(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"), \
             patch("core.notifications.dispatcher.dispatch") as mock_dispatch:
            await notify_high_severity_finding(
                scan_id="s1", target_ref="/r", rule_id="x",
                severity="low", file="app.py", line=1,
            )
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_high_severity_dispatches_for_critical(self):
        with patch("core.notifications.dispatcher._NOTIFY_MIN_SEVERITY", "high"), \
             patch("core.notifications.dispatcher.dispatch") as mock_dispatch:
            mock_dispatch.return_value = None
            await notify_high_severity_finding(
                scan_id="s1", target_ref="/r", rule_id="sqli",
                severity="critical", file="app.py", line=5,
            )
            mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_scan_completed_dispatches(self):
        with patch("core.notifications.dispatcher.dispatch") as mock_dispatch:
            mock_dispatch.return_value = None
            await notify_scan_completed("s1", "/repo", finding_count=7, cost_usd=0.12)
            mock_dispatch.assert_called_once()
            n = mock_dispatch.call_args[0][0]
            assert n.event == NotificationEvent.scan_completed
            assert n.payload["finding_count"] == 7
