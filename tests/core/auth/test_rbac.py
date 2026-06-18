from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends
from core.auth.rbac import require_role


def _make_rbac_app() -> FastAPI:
    """Minimal FastAPI app with two protected endpoints for testing."""
    app = FastAPI()

    @app.get("/analyst-only")
    async def analyst_only(role: str = Depends(require_role("analyst"))):
        return {"role": role}

    @app.get("/admin-only")
    async def admin_only(role: str = Depends(require_role("admin"))):
        return {"role": role}

    @app.get("/viewer-ok")
    async def viewer_ok(role: str = Depends(require_role("viewer"))):
        return {"role": role}

    return app


@pytest.fixture
def rbac_app():
    return _make_rbac_app()


async def test_viewer_blocked_from_analyst_endpoint(rbac_app):
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/analyst-only", headers={"x-argus-role": "viewer"})
    assert resp.status_code == 403
    assert "insufficient" in resp.json()["detail"]


async def test_analyst_passes_analyst_endpoint(rbac_app):
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/analyst-only", headers={"x-argus-role": "analyst"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"


async def test_admin_passes_analyst_endpoint(rbac_app):
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/analyst-only", headers={"x-argus-role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_admin_passes_admin_endpoint(rbac_app):
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/admin-only", headers={"x-argus-role": "admin"})
    assert resp.status_code == 200


async def test_missing_header_defaults_to_viewer_blocked(rbac_app):
    """No X-Argus-Role header => defaults to 'viewer', which is blocked from analyst endpoint."""
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/analyst-only")
    assert resp.status_code == 403


async def test_missing_header_defaults_to_viewer_allowed(rbac_app):
    """No header => defaults to 'viewer', which is allowed on viewer endpoint."""
    async with AsyncClient(transport=ASGITransport(app=rbac_app), base_url="http://test") as c:
        resp = await c.get("/viewer-ok")
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"
