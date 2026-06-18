# tests/core/api/test_config_router.py
from __future__ import annotations
import pytest
import yaml
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


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
async def test_get_config_returns_both_sections(client_with_db):
    client, _ = client_with_db
    resp = await client.get("/api/v1/config/")
    assert resp.status_code == 200
    body = resp.json()
    assert "model_tiers" in body
    assert "budget_policy" in body
    # Verify structure of model tiers
    assert "tiers" in body["model_tiers"]
    # Verify structure of budget policy
    assert "per_scan" in body["budget_policy"]


@pytest.mark.asyncio
async def test_update_budget_policy_validates_positive_limits(client_with_db):
    client, _ = client_with_db
    resp = await client.put("/api/v1/config/budget-policy", json={
        "per_scan": {"soft_limit_usd": -1.0, "hard_limit_usd": 5.0},
        "monthly": {"soft_limit_usd": 160.0, "hard_limit_usd": 200.0},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_budget_policy_writes_audit_entry(client_with_db, tmp_path):
    client, session = client_with_db

    valid_payload = {
        "per_scan": {"soft_limit_usd": 3.0, "hard_limit_usd": 4.0},
        "monthly": {"soft_limit_usd": 120.0, "hard_limit_usd": 150.0},
        "on_soft_limit": "warn",
        "on_hard_limit": "stop_and_mark_skipped",
    }

    with patch("core.api.routers.config._BUDGET_POLICY_PATH", tmp_path / "budget_policy.yaml"):
        (tmp_path / "budget_policy.yaml").write_text(yaml.dump({"per_scan": {}, "monthly": {}}))
        resp = await client.put("/api/v1/config/budget-policy", json=valid_payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    session.add.assert_called_once()  # audit entry
    audit_row = session.add.call_args[0][0]
    assert audit_row.action == "config.update_budget_policy"


@pytest.mark.asyncio
async def test_update_model_tiers_writes_audit_entry(client_with_db, tmp_path):
    client, session = client_with_db

    valid_payload = {
        "providers": {"default": "anthropic"},
        "tiers": {
            "fast": {"anthropic": "claude-haiku-4-5-20251001"},
            "balanced": {"anthropic": "claude-sonnet-4-6"},
            "top": {"anthropic": "claude-opus-4-8"},
        },
        "task_defaults": {"triage": "balanced", "fix_generation": "balanced"},
    }

    with patch("core.api.routers.config._MODEL_TIERS_PATH", tmp_path / "model_tiers.yaml"):
        (tmp_path / "model_tiers.yaml").write_text(yaml.dump({"providers": {}, "tiers": {}, "task_defaults": {}}))
        resp = await client.put("/api/v1/config/model-tiers", json=valid_payload)

    assert resp.status_code == 200
    session.add.assert_called_once()
    audit_row = session.add.call_args[0][0]
    assert audit_row.action == "config.update_model_tiers"


@pytest.mark.asyncio
async def test_update_model_tiers_rejects_empty_tiers(client_with_db):
    client, _ = client_with_db
    resp = await client.put("/api/v1/config/model-tiers", json={
        "providers": {"default": "anthropic"},
        "tiers": {},
        "task_defaults": {},
    })
    assert resp.status_code == 422
