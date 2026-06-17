# core/api/app.py
from __future__ import annotations
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(title="Argus Security Platform", version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    # Stub routes for Phase 2+ (return 501)
    @app.get("/api/v1/pipelines")
    async def list_pipelines():
        return []

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    @app.get("/api/v1/fixes/{fix_id}")
    async def get_fix(fix_id: UUID):
        from fastapi import HTTPException
        raise HTTPException(501, "Fix generation available in Phase 2")

    return app
