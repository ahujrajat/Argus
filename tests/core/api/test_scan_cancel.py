# tests/core/api/test_scan_cancel.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from core.db.tables import ScanRow


@pytest.fixture
async def client_with_db():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()
    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.clear()


async def test_cancel_scan_sets_status_cancelled(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    scan_row = ScanRow(
        id=scan_id,
        target_ref="github.com/org/repo",
        pipeline_config_id=str(uuid4()),
        mode="at_rest",
        approach="penetration_testing",
        status="running",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == scan_id
    assert body["status"] == "cancelled"
    assert scan_row.status == "cancelled"
    assert scan_row.finished_at is not None


async def test_cancel_scan_returns_404_when_not_found(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Scan not found"


async def test_cancel_already_completed_scan_returns_409(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    scan_row = ScanRow(
        id=scan_id,
        target_ref="github.com/org/repo",
        pipeline_config_id=str(uuid4()),
        mode="at_rest",
        approach="penetration_testing",
        status="completed",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()
