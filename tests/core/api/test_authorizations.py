from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from core.api.app import create_app
from core.api.deps import get_db


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── POST /api/v1/authorizations ───────────────────────────────────────────────

async def test_create_authorization_returns_201(app):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/authorizations",
                json={
                    "target": "github.com/acme/myrepo@main",
                    "owner_confirmed": True,
                    "environment": "non-production",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    body = resp.json()
    assert body["target"] == "github.com/acme/myrepo@main"
    assert "id" in body


async def test_create_authorization_rejects_without_owner_confirmed(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/authorizations",
            json={
                "target": "github.com/acme/myrepo@main",
                "owner_confirmed": False,
            },
        )
    assert resp.status_code == 422


# ── GET /api/v1/authorizations ────────────────────────────────────────────────

async def test_list_authorizations_returns_200(app):
    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"
    row.target = "github.com/acme/myrepo@main"
    row.owner_confirmed = True
    row.environment = "non-production"
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=result_mock)

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/authorizations")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── DELETE /api/v1/authorizations/{id} ───────────────────────────────────────

async def test_delete_authorization_returns_204(app):
    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result_mock)
    session.delete = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(
                "/api/v1/authorizations/550e8400-e29b-41d4-a716-446655440000"
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204


async def test_delete_authorization_returns_404_when_missing(app):
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(
                "/api/v1/authorizations/550e8400-e29b-41d4-a716-446655440001"
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
