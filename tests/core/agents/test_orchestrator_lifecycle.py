# tests/core/agents/test_orchestrator_lifecycle.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from core.agents.orchestrator import Orchestrator
from core.model.entities import Scan, ScanMode, SecurityApproach, ModelTier
from core.governance.gate import GateResult
from core.db.tables import ScanRow


def _make_scan() -> Scan:
    return Scan(
        target_ref="/tmp/repo",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
        approach=SecurityApproach.penetration_testing,
    )


def _make_gate_noop() -> MagicMock:
    gate = MagicMock()
    gate.complete = AsyncMock(return_value=GateResult(
        content='{"findings": []}',
        tokens_in=10, tokens_out=5,
        cache_hit=False,
        model_id="claude-haiku-4-5",
        provider="anthropic",
        tier=ModelTier.fast,
        cost_usd=0.0,
    ))
    gate._budget = MagicMock()
    gate._budget.record = MagicMock()
    return gate


async def test_orchestrator_sets_status_running_then_completed():
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest, \
         patch("core.scanners.semgrep.SemgrepAdapter.scan", new_callable=AsyncMock) as mock_semgrep, \
         patch("core.scanners.trufflehog.TruffleHogAdapter.scan", new_callable=AsyncMock) as mock_truffle:
        from core.agents.base import AgentOutput
        mock_ingest.return_value = AgentOutput(agent_id="ingestion", data={"code_context": {}})
        mock_semgrep.return_value = AgentOutput(agent_id="sast", data={"findings": []})
        mock_truffle.return_value = AgentOutput(agent_id="secrets", data={"findings": []})

        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        await orch.run(scan, session)

    assert scan_row.status == "completed"
    assert scan_row.finished_at is not None


async def test_orchestrator_sets_status_failed_on_exception():
    """Outer exceptions (e.g. DB write failure) set status=failed."""
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Patch _persist_findings to raise — this is outside the per-agent try/except
    with patch.object(Orchestrator, "_persist_findings", new_callable=AsyncMock) as mock_persist:
        mock_persist.side_effect = RuntimeError("db write error")
        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest, \
             patch("core.scanners.semgrep.SemgrepAdapter.scan", new_callable=AsyncMock) as mock_semgrep, \
             patch("core.scanners.trufflehog.TruffleHogAdapter.scan", new_callable=AsyncMock) as mock_truffle:
            from core.agents.base import AgentOutput
            mock_ingest.return_value = AgentOutput(agent_id="ingestion", data={"code_context": {}})
            mock_semgrep.return_value = AgentOutput(agent_id="sast", data={"findings": []})
            mock_truffle.return_value = AgentOutput(agent_id="secrets", data={"findings": []})
            with pytest.raises(RuntimeError, match="db write error"):
                await orch.run(scan, session)

    assert scan_row.status == "failed"
    assert scan_row.finished_at is not None


async def test_orchestrator_sets_status_running_at_start():
    """Verify status transitions to 'running' immediately before any agent runs."""
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )
    observed_statuses: list[str] = []

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()

    async def capturing_flush():
        observed_statuses.append(scan_row.status)

    session.flush = capturing_flush

    with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest, \
         patch("core.scanners.semgrep.SemgrepAdapter.scan", new_callable=AsyncMock) as mock_semgrep, \
         patch("core.scanners.trufflehog.TruffleHogAdapter.scan", new_callable=AsyncMock) as mock_truffle:
        from core.agents.base import AgentOutput
        mock_ingest.return_value = AgentOutput(agent_id="ingestion", data={"code_context": {}})
        mock_semgrep.return_value = AgentOutput(agent_id="sast", data={"findings": []})
        mock_truffle.return_value = AgentOutput(agent_id="secrets", data={"findings": []})

        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        await orch.run(scan, session)

    assert "running" in observed_statuses
    assert observed_statuses[0] == "running"
