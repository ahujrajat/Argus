from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch as _patch
from datetime import datetime, timezone


def _make_app(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _mock_session():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


def _policy_row(policy_id="pol-1", name="strict"):
    row = MagicMock()
    row.id = policy_id
    row.name = name
    row.description = "test policy"
    row.active = True
    row.created_by = "api"
    row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.definition = {
        "id": policy_id, "name": name, "description": "test policy",
        "max_critical": 0, "max_high": 5, "max_medium": None,
        "max_low": None, "max_risk_score": None,
        "blocked_owasp": [], "blocked_cwe": [],
        "block_on_any_critical": False, "active": True,
    }
    return row


async def test_create_policy():
    session = _mock_session()
    app = _make_app(session)

    with _patch("core.api.routers.policies.PolicyRow", return_value=_policy_row()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/policies/", json={
                "name": "strict",
                "max_critical": 0,
                "max_high": 5,
                "block_on_any_critical": False,
            })

    assert resp.status_code == 201
    assert resp.json()["name"] == "strict"


async def test_create_policy_rejects_empty_name():
    session = _mock_session()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/policies/", json={"name": "  "})
    assert resp.status_code == 422


async def test_create_policy_rejects_negative_threshold():
    session = _mock_session()
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/policies/", json={"name": "bad", "max_high": -1})
    assert resp.status_code == 422


async def test_list_policies_active_only():
    row = _policy_row()
    inactive = _policy_row(policy_id="pol-2", name="inactive")
    inactive.active = False

    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row, inactive]
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/policies/?active_only=true")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "strict"


async def test_list_policies_all():
    row = _policy_row()
    inactive = _policy_row(policy_id="pol-2", name="inactive")
    inactive.active = False

    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row, inactive]
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/policies/?active_only=false")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_get_policy_not_found():
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/policies/nonexistent")

    assert resp.status_code == 404


async def test_delete_policy():
    row = _policy_row()
    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/v1/policies/pol-1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_evaluate_policy_passes():
    """Evaluate scan with no findings against policy with max_critical=0 — should pass."""
    policy_row = _policy_row()

    scan_row = MagicMock()
    scan_row.id = "11111111-1111-1111-1111-111111111111"
    scan_row.target_ref = "github.com/org/repo"
    scan_row.status = "completed"

    session = _mock_session()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = policy_row
        elif call_count == 2:
            r.scalar_one_or_none.return_value = scan_row
        else:
            r.scalars.return_value.all.return_value = []
        return r

    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with _patch("core.api.routers.policies.PolicyEvaluationRow", return_value=MagicMock(id="eval-1")):
        app = _make_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/policies/pol-1/evaluate/11111111-1111-1111-1111-111111111111"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["violations"] == []


async def test_evaluate_policy_fails_on_critical():
    """Evaluate scan with 2 critical findings against policy with max_critical=0 — should fail."""
    policy_row = _policy_row()

    finding = MagicMock()
    finding.severity = "critical"
    finding.owasp_category = "A03:2021"
    finding.cwe = "CWE-89"

    scan_row = MagicMock()
    scan_row.id = "22222222-2222-2222-2222-222222222222"

    session = _mock_session()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = policy_row
        elif call_count == 2:
            r.scalar_one_or_none.return_value = scan_row
        else:
            r.scalars.return_value.all.return_value = [finding, finding]
        return r

    session.execute = AsyncMock(side_effect=_execute)

    with _patch("core.api.routers.policies.PolicyEvaluationRow", return_value=MagicMock(id="eval-2")):
        app = _make_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/policies/pol-1/evaluate/22222222-2222-2222-2222-222222222222"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert len(data["violations"]) >= 1
