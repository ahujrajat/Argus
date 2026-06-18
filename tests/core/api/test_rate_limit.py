# tests/core/api/test_rate_limit.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_endpoint_accessible():
    """Sanity check that the rate limiter doesn't block normal requests."""
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_metrics_endpoint_accessible():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "argus_" in resp.text


@pytest.mark.asyncio
async def test_limiter_is_registered_on_app():
    from core.api.app import create_app
    app = create_app()
    # slowapi attaches limiter to app.state
    assert hasattr(app.state, "limiter")
