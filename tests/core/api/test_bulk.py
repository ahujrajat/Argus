from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch as _patch


def _make_app(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _finding(fid="f-1", dedup="dk-abc", status="open"):
    row = MagicMock()
    row.id = fid
    row.dedup_key = dedup
    row.status = status
    row.location = {"file": "src/main.py", "line": 10}
    return row


async def test_bulk_suppress_creates_rules():
    f1 = _finding("f-1", "dk-1")
    f2 = _finding("f-2", "dk-2")

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [f1, f2]
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-suppress", json={
            "finding_ids": ["f-1", "f-2"],
            "reason": "known false positive",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["suppressed"] == 2
    assert set(data["suppressed_ids"]) == {"f-1", "f-2"}
    assert data["skipped"] == 0
    # One SuppressionRuleRow add per finding
    assert session.add.call_count == 2
    assert f1.status == "suppressed"
    assert f2.status == "suppressed"


async def test_bulk_suppress_skips_findings_without_dedup_key():
    f1 = _finding("f-1", dedup="dk-1")
    f2 = _finding("f-2", dedup="")  # no dedup_key

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [f1, f2]
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-suppress", json={
            "finding_ids": ["f-1", "f-2"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["suppressed"] == 1
    assert data["skipped"] == 1
    assert "f-2" in data["skipped_ids"]


async def test_bulk_suppress_empty_list_rejected():
    session = AsyncMock()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-suppress", json={"finding_ids": []})
    assert resp.status_code == 422


async def test_bulk_suppress_not_found():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-suppress", json={"finding_ids": ["no-such-id"]})
    assert resp.status_code == 404


async def test_bulk_dismiss():
    f1 = _finding("f-1")
    f2 = _finding("f-2")

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [f1, f2]
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-dismiss", json={
            "finding_ids": ["f-1", "f-2"],
            "reason": "out of scope",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["dismissed"] == 2
    assert f1.status == "dismissed"
    assert f2.status == "dismissed"


async def test_bulk_dismiss_empty_list_rejected():
    session = AsyncMock()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-dismiss", json={"finding_ids": []})
    assert resp.status_code == 422


async def test_bulk_assign():
    f1 = _finding("f-1")
    f2 = _finding("f-2")

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [f1, f2]
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-assign", json={
            "finding_ids": ["f-1", "f-2"],
            "assignee": "alice@example.com",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned"] == 2
    assert data["assignee"] == "alice@example.com"
    assert f1.location["assignee"] == "alice@example.com"
    assert f2.location["assignee"] == "alice@example.com"


async def test_bulk_assign_empty_assignee_rejected():
    session = AsyncMock()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/findings/bulk-assign", json={
            "finding_ids": ["f-1"],
            "assignee": "  ",
        })
    assert resp.status_code == 422
