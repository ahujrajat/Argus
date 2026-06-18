# tests/core/api/test_fixes_router.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from core.api.app import create_app
from core.api.deps import get_db


def _make_fix_row(
    fix_id: str | None = None,
    finding_id: str | None = None,
    status: str = "proposed",
) -> MagicMock:
    row = MagicMock()
    row.id = fix_id or str(uuid4())
    row.finding_id = finding_id or str(uuid4())
    row.diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-bad\n+good\n"
    row.test = None
    row.explanation = "Replaced bad code with good code."
    row.validation_result = None
    row.status = status
    row.reviewer = None
    row.audit_ref = None
    return row


def _make_finding_row(finding_id: str, scan_id: str) -> MagicMock:
    row = MagicMock()
    row.id = finding_id
    row.scan_id = scan_id
    return row


def _make_mock_db(scalar_result=None, scalars_result=None):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_result.scalars.return_value.all.return_value = scalars_result or []
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    return mock_db


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_scan_fixes_returns_list(app):
    scan_id = str(uuid4())
    finding_id = str(uuid4())
    fix_row = _make_fix_row(finding_id=finding_id)
    mock_db = _make_mock_db(scalars_result=[fix_row])

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/scans/{scan_id}/fixes")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == fix_row.id
    assert data[0]["status"] == "proposed"


async def test_get_fix_returns_detail(app):
    fix_row = _make_fix_row()
    mock_db = _make_mock_db(scalar_result=fix_row)

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/fixes/{fix_row.id}")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["diff"] == fix_row.diff
    assert data["explanation"] == fix_row.explanation


async def test_get_fix_returns_404_when_not_found(app):
    mock_db = _make_mock_db(scalar_result=None)

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/fixes/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


async def test_apply_fix_writes_audit_log_before_status_change(app):
    fix_id = str(uuid4())
    fix_row = _make_fix_row(fix_id=fix_id, status="proposed")
    mock_db = _make_mock_db(scalar_result=fix_row)

    call_order: list[str] = []

    def track_add(obj):
        from core.db.tables import AuditLogEntryRow
        if isinstance(obj, AuditLogEntryRow):
            call_order.append("audit_written")
        call_order.append(f"add:{type(obj).__name__}")

    mock_db.add = MagicMock(side_effect=track_add)
    mock_db.commit = AsyncMock(side_effect=lambda: call_order.append("committed"))

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/v1/fixes/{fix_id}/apply")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    assert "audit_written" in call_order
    assert fix_row.status == "applied"


async def test_apply_fix_returns_404_when_not_found(app):
    mock_db = _make_mock_db(scalar_result=None)

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/v1/fixes/{uuid4()}/apply")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


async def test_reject_fix_writes_audit_log_with_reason(app):
    fix_id = str(uuid4())
    fix_row = _make_fix_row(fix_id=fix_id, status="proposed")
    mock_db = _make_mock_db(scalar_result=fix_row)

    audit_entries: list = []
    mock_db.add = MagicMock(side_effect=lambda obj: audit_entries.append(obj))

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/fixes/{fix_id}/reject",
                json={"reason": "Fix introduces regression"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert fix_row.status == "rejected"
    from core.db.tables import AuditLogEntryRow
    audit_row = next(
        (e for e in audit_entries if isinstance(e, AuditLogEntryRow)), None
    )
    assert audit_row is not None
    assert audit_row.action == "fix_reject"
    assert audit_row.after["reason"] == "Fix introduces regression"


async def test_reject_fix_returns_404_when_not_found(app):
    mock_db = _make_mock_db(scalar_result=None)

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/v1/fixes/{uuid4()}/reject", json={"reason": "nope"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
