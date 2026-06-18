from __future__ import annotations
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from core.governance.events import ScanEventBus


async def test_sse_receives_events():
    from core.api.app import create_app
    bus = ScanEventBus()
    app = create_app(event_bus=bus)
    scan_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def emit_events():
            await asyncio.sleep(0.05)
            bus.emit(scan_id, {"event": "agent_started", "agent": "triage"})
            bus.emit(scan_id, {"event": "scan_completed", "total_cost_usd": 0.01})

        asyncio.create_task(emit_events())

        lines = []
        async with client.stream("GET", f"/api/v1/scans/{scan_id}/events") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    lines.append(line)
                if len(lines) >= 2:
                    break

    assert any("agent_started" in l for l in lines)
    assert any("scan_completed" in l for l in lines)
