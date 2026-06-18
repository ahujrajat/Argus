# tests/core/api/test_scan_batch.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from core.db.tables import PipelineConfigRow


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


def _make_pc_row(name: str) -> PipelineConfigRow:
    return PipelineConfigRow(
        id=str(uuid4()),
        name=name,
        version=1,
        definition={"nodes": [], "edges": []},
        is_default=False,
        is_factory=False,
    )


@pytest.mark.asyncio
async def test_batch_scan_dispatches_all_targets(client_with_db):
    client, session = client_with_db

    full_scan_row = _make_pc_row("full-scan")
    sca_row = _make_pc_row("sca-scan")

    execute_calls = iter([
        MagicMock(**{"scalar_one_or_none.return_value": full_scan_row}),
        MagicMock(**{"scalar_one_or_none.return_value": sca_row}),
    ])
    session.execute = AsyncMock(side_effect=lambda *a, **kw: next(execute_calls))
    session.flush = AsyncMock()
    session.add = MagicMock()

    mock_orch_instance = MagicMock()
    mock_orch_instance.run = AsyncMock(return_value=[])

    with patch("core.governance.gate.GovernanceGate"), \
         patch("core.agents.orchestrator.Orchestrator", return_value=mock_orch_instance), \
         patch("core.db.session.get_session") as mock_gs:
        mock_sess = AsyncMock()
        mock_gs.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_gs.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = await client.post("/api/v1/scans/batch", json={
            "scans": [
                {"target_ref": "/repo/a", "pipeline_config_name": "full-scan"},
                {"target_ref": "/repo/b", "pipeline_config_name": "sca-scan"},
            ]
        })

    assert resp.status_code == 202
    body = resp.json()
    assert "batch_id" in body
    assert len(body["scan_ids"]) == 2
    assert body["status"] == "accepted"


@pytest.mark.asyncio
async def test_batch_scan_returns_404_for_unknown_pipeline(client_with_db):
    client, session = client_with_db

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.post("/api/v1/scans/batch", json={
        "scans": [
            {"target_ref": "/repo", "pipeline_config_name": "does-not-exist"},
        ]
    })

    assert resp.status_code == 404
    assert "does-not-exist" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_batch_scan_rejects_empty_list(client_with_db):
    client, session = client_with_db

    resp = await client.post("/api/v1/scans/batch", json={"scans": []})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_scan_validates_all_pipelines_before_inserting(client_with_db):
    """If the second pipeline name is unknown, the first scan should not be inserted."""
    client, session = client_with_db

    full_scan_row = _make_pc_row("full-scan")
    execute_calls = iter([
        MagicMock(**{"scalar_one_or_none.return_value": full_scan_row}),
        MagicMock(**{"scalar_one_or_none.return_value": None}),  # second pipeline missing
    ])
    session.execute = AsyncMock(side_effect=lambda *a, **kw: next(execute_calls))
    session.flush = AsyncMock()
    session.add = MagicMock()

    resp = await client.post("/api/v1/scans/batch", json={
        "scans": [
            {"target_ref": "/repo/a", "pipeline_config_name": "full-scan"},
            {"target_ref": "/repo/b", "pipeline_config_name": "missing-pipeline"},
        ]
    })

    assert resp.status_code == 404
    # No rows should have been inserted
    session.add.assert_not_called()
