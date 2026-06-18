from __future__ import annotations
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch as _patch


def _sched_row(cron_expr="* * * * *"):
    from core.db.tables import ScheduledScanRow
    now = datetime.now(timezone.utc)
    row = ScheduledScanRow(
        id="sched-1",
        name="test-schedule",
        cron_expr=cron_expr,
        pipeline_config_name="full-scan",
        target_ref="github.com/org/repo",
        enabled=True,
        last_run_at=None,
        next_run_at=now - timedelta(seconds=1),  # overdue
        created_at=now,
    )
    return row


async def test_tick_enqueues_scan():
    from core.scheduler.runner import _tick

    sched = _sched_row()
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sched]
    db.execute = AsyncMock(return_value=mock_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with _patch("core.scheduler.runner.get_session", return_value=mock_cm):
        await _tick(datetime.now(timezone.utc))

    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert sched.last_run_at is not None
    assert sched.next_run_at is not None
    assert sched.next_run_at > sched.last_run_at


async def test_tick_no_due_schedules():
    from core.scheduler.runner import _tick

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with _patch("core.scheduler.runner.get_session", return_value=mock_cm):
        await _tick(datetime.now(timezone.utc))

    db.add.assert_not_called()
    db.flush.assert_not_called()


async def test_scheduler_loop_cancels_cleanly():
    from core.scheduler.runner import scheduler_loop

    mock_cm = AsyncMock()
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)
    mock_cm.__aenter__ = AsyncMock(return_value=db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with _patch("core.scheduler.runner.get_session", return_value=mock_cm), \
         _patch("core.scheduler.runner._TICK_SECONDS", 0.01):
        task = asyncio.create_task(scheduler_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # expected
