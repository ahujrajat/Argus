# tests/core/api/test_pipelines.py
from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from core.api.app import create_app
from core.api.deps import get_db

PIPELINE_ID = str(uuid.uuid4())
PIPELINE_ID_2 = str(uuid.uuid4())


def _make_row(
    pid: str = PIPELINE_ID,
    name: str = "custom-scan",
    is_factory: bool = False,
    is_default: bool = False,
    version: int = 1,
    definition: dict | None = None,
):
    row = MagicMock()
    row.id = pid
    row.name = name
    row.version = version
    row.is_factory = is_factory
    row.is_default = is_default
    row.definition = definition or {
        "nodes": [{"id": "n1", "agent": "TriageAgent", "tier": "fast", "budget_pct": 100}],
        "edges": [],
    }
    row.created_at = None
    return row


def _override(rows: list | None = None, single: object = None):
    """Helper that builds an app with DB overridden."""
    app = create_app()
    session = AsyncMock()

    if rows is not None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result)
    else:
        result = MagicMock()
        result.scalar_one_or_none.return_value = single
        session.execute = AsyncMock(return_value=result)

    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    return app, session


# ── list ──────────────────────────────────────────────────────────────────────

async def test_list_pipelines_returns_200():
    app, _ = _override(rows=[_make_row(), _make_row(pid=PIPELINE_ID_2, name="pr-check")])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/pipelines")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── get ───────────────────────────────────────────────────────────────────────

async def test_get_pipeline_returns_200():
    app, _ = _override(single=_make_row())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/pipelines/{PIPELINE_ID}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "custom-scan"


async def test_get_pipeline_returns_404_when_missing():
    app, _ = _override(single=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/pipelines/{PIPELINE_ID}")
    assert resp.status_code == 404


# ── create ────────────────────────────────────────────────────────────────────

async def test_create_pipeline_returns_201():
    app, _ = _override(single=None)  # name-conflict check returns None
    body = {
        "name": "my-pipeline",
        "definition": {
            "nodes": [{"id": "n1", "agent": "TriageAgent", "tier": "fast", "budget_pct": 100}],
            "edges": [],
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/pipelines", json=body)
    assert resp.status_code == 201


async def test_create_pipeline_rejects_budget_over_100():
    app, _ = _override(single=None)
    body = {
        "name": "bad-budget",
        "definition": {
            "nodes": [
                {"id": "n1", "agent": "A", "tier": "fast", "budget_pct": 60},
                {"id": "n2", "agent": "B", "tier": "fast", "budget_pct": 60},
            ],
            "edges": [],
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/pipelines", json=body)
    assert resp.status_code == 422


# ── update ────────────────────────────────────────────────────────────────────

async def test_update_pipeline_returns_200():
    row = _make_row()
    app, _ = _override(single=row)
    body = {
        "definition": {
            "nodes": [{"id": "n1", "agent": "TriageAgent", "tier": "balanced", "budget_pct": 100}],
            "edges": [],
        }
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.put(f"/api/v1/pipelines/{PIPELINE_ID}", json=body)
    assert resp.status_code == 200


async def test_update_factory_pipeline_returns_403():
    row = _make_row(is_factory=True)
    app, _ = _override(single=row)
    body = {"definition": {"nodes": [], "edges": []}}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.put(f"/api/v1/pipelines/{PIPELINE_ID}", json=body)
    assert resp.status_code == 403


# ── delete ────────────────────────────────────────────────────────────────────

async def test_delete_pipeline_returns_204():
    row = _make_row()
    app, session = _override(single=row)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/pipelines/{PIPELINE_ID}")
    assert resp.status_code == 204


async def test_delete_factory_pipeline_returns_403():
    row = _make_row(is_factory=True)
    app, _ = _override(single=row)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/pipelines/{PIPELINE_ID}")
    assert resp.status_code == 403


# ── clone ─────────────────────────────────────────────────────────────────────

async def test_clone_pipeline_returns_201():
    row = _make_row()
    app, _ = _override(single=row)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/pipelines/{PIPELINE_ID}/clone", json={"name": "custom-scan-copy"})
    assert resp.status_code == 201


async def test_clone_returns_404_when_source_missing():
    app, _ = _override(single=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/pipelines/{PIPELINE_ID}/clone", json={"name": "custom-scan-copy"})
    assert resp.status_code == 404
