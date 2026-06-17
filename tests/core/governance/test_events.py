from __future__ import annotations
import asyncio
import pytest
from uuid import uuid4
from core.governance.events import ScanEventBus


async def test_emit_and_receive():
    bus = ScanEventBus()
    scan_id = uuid4()
    received = []

    async def collect():
        async for event in bus.subscribe(scan_id):
            received.append(event)
            if event.get("event") == "scan_completed":
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.01)
    bus.emit(scan_id, {"event": "agent_started", "agent": "triage"})
    bus.emit(scan_id, {"event": "scan_completed"})
    await task

    assert len(received) == 2
    assert received[0]["event"] == "agent_started"
