# core/api/sse.py
from __future__ import annotations
import json
from uuid import UUID
from sse_starlette.sse import EventSourceResponse
from core.governance.events import ScanEventBus


def scan_event_stream(scan_id: UUID, bus: ScanEventBus):
    async def generator():
        async for event in bus.subscribe(scan_id):
            yield {"data": json.dumps(event, default=str)}

    return EventSourceResponse(generator())
