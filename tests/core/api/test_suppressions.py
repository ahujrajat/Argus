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


def _make_client_with_db(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


async def test_create_suppression_fingerprint():
    from unittest.mock import patch as _patch

    row = MagicMock()
    row.id = "aaa"
    row.pattern_type = "fingerprint"
    row.pattern = "abc123"
    row.reason = "Known FP"
    row.created_by = "api"
    row.expires_at = None
    row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    session = _mock_session()
    app = _make_client_with_db(session)

    with _patch("core.api.routers.suppressions.SuppressionRuleRow", return_value=row):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/suppressions/", json={
                "pattern_type": "fingerprint",
                "pattern": "abc123",
                "reason": "Known FP",
            })

    assert resp.status_code == 201
    data = resp.json()
    assert data["pattern_type"] == "fingerprint"
    assert data["pattern"] == "abc123"


async def test_create_suppression_rejects_empty_pattern():
    session = _mock_session()
    app = _make_client_with_db(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/suppressions/", json={
            "pattern_type": "path_glob",
            "pattern": "   ",
        })
    assert resp.status_code == 422


async def test_create_suppression_rejects_invalid_type():
    session = _mock_session()
    app = _make_client_with_db(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/suppressions/", json={
            "pattern_type": "invalid_type",
            "pattern": "tests/**",
        })
    assert resp.status_code == 422


async def test_list_suppressions_empty():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_client_with_db(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/suppressions/")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_delete_suppression_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_client_with_db(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/suppressions/nonexistent")

    assert resp.status_code == 404
