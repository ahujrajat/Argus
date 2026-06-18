from __future__ import annotations
import pytest
import yaml
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import core.agents.orchestrator as orch_module
from core.model.entities import Scan, ScanMode
from core.db.tables import TargetAuthorizationRow
from core.agents.base import AgentOutput


_DAST_PIPELINE = """
name: dast-scan
version: 1
nodes:
  - id: dast
    agent: NucleiAdapter
    tier: none
    budget_pct: 0
edges: []
"""


def _make_scan(target: str = "https://app.example.com") -> Scan:
    return Scan(target_ref=target, pipeline_config_id=uuid4(), mode=ScanMode.at_rest)


def _make_orch() -> orch_module.Orchestrator:
    raw = yaml.safe_load(_DAST_PIPELINE)
    orch = orch_module.Orchestrator.__new__(orch_module.Orchestrator)
    orch._gate = MagicMock()
    orch._ledger = MagicMock()
    orch._ledger.record = AsyncMock()
    orch._pipeline = raw
    orch._nodes = {n["id"]: n for n in raw["nodes"]}
    orch._edges = raw.get("edges", [])
    return orch


def _make_session(scan_row=None, auth_row=None):
    session = AsyncMock()
    scan_res = MagicMock()
    scan_res.scalar_one_or_none.return_value = scan_row
    auth_res = MagicMock()
    auth_res.scalar_one_or_none.return_value = auth_row
    session.execute = AsyncMock(side_effect=iter([scan_res, auth_res]))
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


class _FakeNuclei:
    """Fake NucleiAdapter that captures ctx without shelling out."""
    agent_id = "dast_nuclei"
    captured: list

    def __init__(self):
        _FakeNuclei.captured = []

    async def scan(self, ctx):
        _FakeNuclei.captured.append(ctx)
        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": []},
            cost_usd=0.0,
            skipped=True,
            skip_reason="test_stub",
        )


@pytest.mark.asyncio
async def test_dast_node_authorized_when_valid_auth_exists():
    auth_row = TargetAuthorizationRow(
        id=str(uuid4()),
        target="https://app.example.com",
        owner_confirmed=True,
        environment="non-production",
        expires_at=None,
    )
    session = _make_session(auth_row=auth_row)

    with patch.dict(orch_module._AGENT_REGISTRY, {"NucleiAdapter": _FakeNuclei}):
        await _make_orch().run(_make_scan(), session)

    assert _FakeNuclei.captured, "NucleiAdapter.scan was never called"
    assert _FakeNuclei.captured[0].extra.get("dast_authorized") is True


@pytest.mark.asyncio
async def test_dast_node_not_authorized_when_no_auth_row():
    session = _make_session(auth_row=None)

    with patch.dict(orch_module._AGENT_REGISTRY, {"NucleiAdapter": _FakeNuclei}):
        await _make_orch().run(_make_scan(), session)

    assert _FakeNuclei.captured, "NucleiAdapter.scan was never called"
    assert _FakeNuclei.captured[0].extra.get("dast_authorized") is False


@pytest.mark.asyncio
async def test_dast_node_not_authorized_when_auth_expired():
    auth_row = TargetAuthorizationRow(
        id=str(uuid4()),
        target="https://app.example.com",
        owner_confirmed=True,
        environment="non-production",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    session = _make_session(auth_row=auth_row)

    with patch.dict(orch_module._AGENT_REGISTRY, {"NucleiAdapter": _FakeNuclei}):
        await _make_orch().run(_make_scan(), session)

    assert _FakeNuclei.captured
    assert _FakeNuclei.captured[0].extra.get("dast_authorized") is False


@pytest.mark.asyncio
async def test_non_dast_pipeline_skips_auth_check():
    """When the pipeline has no DAST nodes, no auth DB query is issued."""
    non_dast_raw = yaml.safe_load("""
name: sast-only
version: 1
nodes:
  - id: sast
    agent: SemgrepAdapter
    tier: none
    budget_pct: 0
edges: []
""")
    orch = orch_module.Orchestrator.__new__(orch_module.Orchestrator)
    orch._gate = MagicMock()
    orch._ledger = MagicMock()
    orch._ledger.record = AsyncMock()
    orch._pipeline = non_dast_raw
    orch._nodes = {n["id"]: n for n in non_dast_raw["nodes"]}
    orch._edges = []

    session = AsyncMock()
    # ScanRow lookup → None
    scan_res = MagicMock()
    scan_res.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=scan_res)
    session.flush = AsyncMock()
    session.add = MagicMock()

    captured_semgrep: list = []

    class _FakeSemgrep:
        agent_id = "sast_semgrep"

        async def scan(self, ctx):
            captured_semgrep.append(ctx)
            return AgentOutput(agent_id=self.agent_id, data={"findings": []}, cost_usd=0.0)

    with patch.dict(orch_module._AGENT_REGISTRY, {"SemgrepAdapter": _FakeSemgrep}):
        await orch.run(Scan(target_ref="/repo", pipeline_config_id=uuid4(), mode=ScanMode.at_rest), session)

    # Session.execute called only once (for ScanRow, not for auth check)
    assert session.execute.call_count == 1
    assert "dast_authorized" not in captured_semgrep[0].extra
