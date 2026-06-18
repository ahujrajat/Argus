# core/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
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
from core.api.routers.auth import router as auth_router
from core.api.routers.suppressions import router as suppressions_router
from core.api.routers.schedules import router as schedules_router
from core.api.routers.policies import router as policies_router
from core.api.routers.bulk import router as bulk_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus
from core.db.seed import seed_pipeline_configs
from core.db.session import get_session
from core.observability.metrics import metrics_text

# Rate limiter — 60 requests/minute per IP by default
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from core.scheduler.runner import scheduler_loop

        async with get_session() as session:
            await seed_pipeline_configs(session)

        scheduler_task = asyncio.create_task(scheduler_loop())
        yield
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="Argus Security Platform", version="0.2.0", docs_url="/docs", lifespan=lifespan)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(suppressions_router, prefix="/api/v1")
    app.include_router(schedules_router, prefix="/api/v1")
    app.include_router(policies_router, prefix="/api/v1")
    app.include_router(bulk_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def prometheus_metrics():
        body, content_type = metrics_text()
        return Response(content=body, media_type=content_type)

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    return app

# Module-level instance for uvicorn
app = create_app()
