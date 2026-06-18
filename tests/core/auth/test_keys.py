# tests/core/auth/test_keys.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from core.auth.keys import generate_key, _hash


class TestGenerateKey:
    def test_returns_raw_and_hash(self):
        raw, hashed = generate_key()
        assert raw.startswith("argus_")
        assert hashed == _hash(raw)

    def test_unique_each_call(self):
        raw1, _ = generate_key()
        raw2, _ = generate_key()
        assert raw1 != raw2

    def test_hash_is_deterministic(self):
        raw, h1 = generate_key()
        h2 = _hash(raw)
        assert h1 == h2

    def test_hash_length(self):
        _, hashed = generate_key()
        assert len(hashed) == 64  # SHA-256 hex


def _make_key_row(revoked=False, expires_at=None):
    from core.db.tables import ApiKeyRow
    row = MagicMock(spec=ApiKeyRow)
    row.id = str(uuid4())
    row.name = "test-key"
    row.key_hash = "somehash"
    row.revoked = revoked
    row.expires_at = expires_at
    return row


@pytest.fixture
async def client_with_db():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_api_key_returns_raw_key(client_with_db):
    client, session = client_with_db
    resp = await client.post("/api/v1/auth/keys", json={"name": "ci-key", "created_by": "admin"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"].startswith("argus_")
    assert "id" in body
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_list_keys_requires_auth(client_with_db):
    client, _ = client_with_db
    resp = await client.get("/api/v1/auth/keys")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_revoke_key_returns_404_if_missing(client_with_db):
    client, session = client_with_db
    fake_id = str(uuid4())

    # auth: valid key row returned for the Bearer token
    valid_row = _make_key_row()
    mock_result_auth = MagicMock()
    mock_result_auth.scalar_one_or_none.return_value = valid_row

    # revoke: key not found
    mock_result_not_found = MagicMock()
    mock_result_not_found.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[mock_result_auth, mock_result_not_found])

    resp = await client.delete(
        f"/api/v1/auth/keys/{fake_id}",
        headers={"Authorization": "Bearer argus_somekey"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_key_succeeds(client_with_db):
    client, session = client_with_db
    key_id = str(uuid4())

    valid_row = _make_key_row()
    target_row = _make_key_row()
    target_row.id = key_id

    results = [
        MagicMock(**{"scalar_one_or_none.return_value": valid_row}),
        MagicMock(**{"scalar_one_or_none.return_value": target_row}),
    ]
    session.execute = AsyncMock(side_effect=results)

    resp = await client.delete(
        f"/api/v1/auth/keys/{key_id}",
        headers={"Authorization": "Bearer argus_somekey"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_master_key_bypass(client_with_db):
    client, session = client_with_db
    master = "argus_master_bypass_key"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch("core.auth.keys._ARGUS_MASTER_KEY", master):
        resp = await client.get(
            "/api/v1/auth/keys",
            headers={"Authorization": f"Bearer {master}"},
        )
    assert resp.status_code == 200
