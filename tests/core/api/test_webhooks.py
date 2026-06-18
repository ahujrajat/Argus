# tests/core/api/test_webhooks.py
from __future__ import annotations
import json
import hashlib
import hmac
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from uuid import uuid4


def _make_pipeline_row(name: str = "pr-check"):
    row = MagicMock()
    row.id = str(uuid4())
    row.name = name
    return row


@pytest.fixture
async def client_with_db():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_pipeline_row()
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_github_push_webhook_enqueues_scan(client_with_db):
    client, session = client_with_db
    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert "scan_id" in body
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_github_pr_webhook_enqueues_scan(client_with_db):
    client, _ = client_with_db
    payload = {
        "action": "opened",
        "pull_request": {
            "head": {
                "ref": "feature/my-branch",
                "repo": {"clone_url": "https://github.com/org/repo.git"},
            }
        },
    }
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_github_ignores_non_push_events(client_with_db):
    client, session = client_with_db
    payload = {"action": "labeled"}
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "issues", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    session.add.assert_not_called()


def test_github_signature_verification_passes_with_correct_secret():
    from core.api.routers.webhooks import _verify_github_signature
    import hmac as _hmac, hashlib as _hashlib
    body = b'{"ref": "refs/heads/main"}'
    secret = "mysecret"
    sig = "sha256=" + _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
    with patch("core.api.routers.webhooks._GITHUB_SECRET", secret):
        assert _verify_github_signature(body, sig)


def test_github_signature_verification_rejects_wrong_secret():
    from core.api.routers.webhooks import _verify_github_signature
    body = b'{"ref": "refs/heads/main"}'
    with patch("core.api.routers.webhooks._GITHUB_SECRET", "mysecret"):
        assert not _verify_github_signature(body, "sha256=invalidsig")


@pytest.mark.asyncio
async def test_gitlab_push_webhook_enqueues_scan(client_with_db):
    client, session = client_with_db
    payload = {
        "object_kind": "push",
        "ref": "refs/heads/main",
        "repository": {"git_http_url": "https://gitlab.com/org/repo.git"},
    }
    resp = await client.post(
        "/api/v1/webhooks/gitlab",
        content=json.dumps(payload),
        headers={"X-Gitlab-Event": "Push Hook", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_gitlab_ignores_unknown_events(client_with_db):
    client, session = client_with_db
    resp = await client.post(
        "/api/v1/webhooks/gitlab",
        content=json.dumps({}),
        headers={"X-Gitlab-Event": "Tag Push Hook", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_github_returns_503_when_pipeline_not_found(client_with_db):
    client, session = client_with_db
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert resp.status_code == 503
