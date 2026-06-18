# core/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.routers.fixes import router as fixes_router
from core.api.routers.authorizations import router as authorizations_router
from core.api.routers.pipelines import router as pipelines_router
from core.api.routers.skills import router as skills_router
from core.api.routers.audit import router as audit_router
from core.api.routers.config import router as config_router
from core.api.routers.webhooks import router as webhooks_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus
from core.db.seed import seed_pipeline_configs
from core.db.session import get_session


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with get_session() as session:
            await seed_pipeline_configs(session)
        yield

    app = FastAPI(title="Argus Security Platform", version="0.2.0", docs_url="/docs", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")
    app.include_router(fixes_router, prefix="/api/v1")
    app.include_router(authorizations_router, prefix="/api/v1")
    app.include_router(pipelines_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(webhooks_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    return app

# Module-level instance for uvicorn
app = create_app()
