from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch as _patch
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


def _make_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", "sched-1")
    row.name = overrides.get("name", "nightly")
    row.cron_expr = overrides.get("cron_expr", "0 2 * * *")
    row.pipeline_config_name = overrides.get("pipeline_config_name", "full-scan")
    row.target_ref = overrides.get("target_ref", "github.com/org/repo")
    row.enabled = overrides.get("enabled", True)
    row.last_run_at = overrides.get("last_run_at", None)
    row.next_run_at = overrides.get("next_run_at", None)
    row.created_at = overrides.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return row


async def test_create_schedule():
    row = _make_row()
    session = _mock_session()
    app = _make_app(session)

    with _patch("core.api.routers.schedules.ScheduledScanRow", return_value=row):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/schedules/", json={
                "name": "nightly",
                "cron_expr": "0 2 * * *",
                "pipeline_config_name": "full-scan",
                "target_ref": "github.com/org/repo",
            })

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "nightly"
    assert data["cron_expr"] == "0 2 * * *"


async def test_create_schedule_rejects_invalid_cron():
    session = _mock_session()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/schedules/", json={
            "name": "bad",
            "cron_expr": "not a cron",
            "pipeline_config_name": "full-scan",
            "target_ref": "repo",
        })
    assert resp.status_code == 422


async def test_list_schedules():
    row = _make_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/schedules/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "nightly"


async def test_get_schedule_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/schedules/missing-id")

    assert resp.status_code == 404


async def test_enable_schedule():
    row = _make_row(enabled=False, next_run_at=None)
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/schedules/sched-1/enable")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["next_run_at"] is not None


async def test_disable_schedule():
    row = _make_row(enabled=True)
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/schedules/sched-1/disable")

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert resp.json()["next_run_at"] is None


async def test_delete_schedule():
    row = _make_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=mock_result)
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/schedules/sched-1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
