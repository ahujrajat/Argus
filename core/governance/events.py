from __future__ import annotations
import asyncio
from uuid import UUID
from typing import AsyncGenerator


class ScanEventBus:
    def __init__(self) -> None:
        self._queues: dict[UUID, list[asyncio.Queue]] = {}

    def emit(self, scan_id: UUID, event: dict) -> None:
        for q in self._queues.get(scan_id, []):
            q.put_nowait(event)

    async def subscribe(self, scan_id: UUID) -> AsyncGenerator[dict, None]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(scan_id, []).append(q)
        try:
            while True:
                event = await q.get()
                yield event
                if event.get("event") in ("scan_completed", "scan_failed", "scan_cancelled"):
                    break
        finally:
            self._queues[scan_id].remove(q)
            if not self._queues[scan_id]:
                del self._queues[scan_id]


event_bus = ScanEventBus()
