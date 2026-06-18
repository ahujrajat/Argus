from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


def _mock_session():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_app(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _make_org_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", "org-1")
    row.name = overrides.get("name", "Acme Corp")
    row.slug = overrides.get("slug", "acme-corp")
    row.created_at = overrides.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return row


def _make_member_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", "mem-1")
    row.org_id = overrides.get("org_id", "org-1")
    row.user_id = overrides.get("user_id", "user-42")
    row.role = overrides.get("role", "viewer")
    row.created_at = overrides.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return row


# ── Org CRUD ──────────────────────────────────────────────────────────────────

async def test_create_org():
    org = _make_org_row()
    session = _mock_session()
    app = _make_app(session)

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "core.api.routers.orgs.OrgRow", return_value=org
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/orgs/", json={"name": "Acme Corp", "slug": "acme-corp"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"


async def test_create_org_invalid_slug():
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/orgs/", json={"name": "Bad Org", "slug": "Bad Slug!!"})

    assert resp.status_code == 422


async def test_create_org_slug_with_uppercase_rejected():
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/orgs/", json={"name": "Org", "slug": "MyOrg"})

    assert resp.status_code == 422


async def test_list_orgs():
    org = _make_org_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [org]
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/orgs/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["slug"] == "acme-corp"


async def test_get_org():
    org = _make_org_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = org
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/orgs/org-1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "org-1"


async def test_get_org_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/orgs/missing")

    assert resp.status_code == 404


async def test_delete_org():
    org = _make_org_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = org
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/orgs/org-1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_delete_org_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/orgs/ghost")

    assert resp.status_code == 404


# ── Member CRUD ───────────────────────────────────────────────────────────────

async def test_add_member():
    org = _make_org_row()
    member = _make_member_row(role="analyst")
    session = _mock_session()

    # First execute call returns org (for existence check), second would be member
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    session.execute = AsyncMock(return_value=org_result)

    app = _make_app(session)

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "core.api.routers.orgs.OrgMemberRow", return_value=member
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/orgs/org-1/members", json={"user_id": "user-42", "role": "analyst"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == "user-42"
    assert data["role"] == "analyst"


async def test_list_members():
    member = _make_member_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [member]
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/orgs/org-1/members")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "user-42"


async def test_remove_member():
    member = _make_member_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = member
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/orgs/org-1/members/mem-1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_remove_member_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/orgs/org-1/members/ghost")

    assert resp.status_code == 404
