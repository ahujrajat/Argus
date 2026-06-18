# core/scheduler/runner.py
"""Background asyncio task that fires scheduled scans when their cron triggers."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from croniter import croniter
from sqlalchemy import select

from core.db.session import get_session
from core.db.tables import ScheduledScanRow, ScanRow

log = structlog.get_logger(__name__)

_TICK_SECONDS = 30  # how often to poll for due schedules
_running = False


async def _tick(now: datetime) -> None:
    """Check for due schedules and enqueue a scan for each."""
    async with get_session() as session:
        result = await session.execute(
            select(ScheduledScanRow).where(
                ScheduledScanRow.enabled == True,  # noqa: E712
                ScheduledScanRow.next_run_at <= now,
            )
        )
        due = result.scalars().all()

        for sched in due:
            scan = ScanRow(
                id=str(uuid4()),
                target_ref=sched.target_ref,
                pipeline_config_id=sched.id,  # logical link; orchestrator resolves by name
                mode="at_rest",
                approach="penetration_testing",
                status="pending",
            )
            session.add(scan)
            sched.last_run_at = now
            it = croniter(sched.cron_expr, now)
            sched.next_run_at = it.get_next(datetime)
            await session.flush()
            log.info(
                "scheduled_scan_enqueued",
                schedule_id=sched.id,
                schedule_name=sched.name,
                scan_id=scan.id,
                next_run_at=sched.next_run_at.isoformat(),
            )


async def scheduler_loop() -> None:
    """Main loop. Call once from app lifespan; cancellation stops it."""
    global _running
    _running = True
    log.info("scheduler_started", tick_seconds=_TICK_SECONDS)
    try:
        while True:
            try:
                await _tick(datetime.now(timezone.utc))
            except Exception:
                log.exception("scheduler_tick_error")
            await asyncio.sleep(_TICK_SECONDS)
    except asyncio.CancelledError:
        log.info("scheduler_stopped")
        _running = False


def is_running() -> bool:
    return _running
