from __future__ import annotations
import pytest
from uuid import uuid4
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from core.agents.orchestrator import Orchestrator
from core.model.entities import Scan, ScanMode, ModelTier
from core.governance.gate import GateResult


MOCK_TRIAGE_RESPONSE = '''{
  "findings": [{
    "dedup_key": "semgrep:python.lang.security.audit.formatted-sql-query.formatted-sql-query:app.py:5",
    "confidence": 0.9, "exploit_likelihood": 0.85,
    "reachability": "reachable from HTTP input",
    "attack_scenario": "Attacker injects SQL via username parameter.",
    "priority_score": 9.0, "status": "open",
    "false_positive_reason": null, "attack_chain": null
  }]
}'''

MOCK_EXPLAIN_RESPONSE = '''{
  "explanations": [{
    "dedup_key": "semgrep:python.lang.security.audit.formatted-sql-query.formatted-sql-query:app.py:5",
    "explanation": "Attacker injects SQL via username. String interpolation at app.py:5 is unsanitized. Fix: use parameterized queries."
  }]
}'''


@pytest.fixture
def mock_gate():
    gate = MagicMock()
    gate.complete = AsyncMock(side_effect=[
        GateResult(content=MOCK_TRIAGE_RESPONSE, tokens_in=800, tokens_out=200,
                   cache_hit=False, model_id="claude-sonnet-4-6", provider="anthropic",
                   tier=ModelTier.balanced, cost_usd=0.006),
        GateResult(content=MOCK_EXPLAIN_RESPONSE, tokens_in=400, tokens_out=100,
                   cache_hit=False, model_id="claude-haiku-4-5-20251001", provider="anthropic",
                   tier=ModelTier.fast, cost_usd=0.001),
    ])
    gate._budget = MagicMock()
    gate._budget.record = MagicMock()
    return gate


async def test_orchestrator_runs_full_pipeline(mock_gate):
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.add = MagicMock()
    session.flush = AsyncMock()

    orch = Orchestrator(gate=mock_gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
    findings = await orch.run(scan, session)

    assert isinstance(findings, list)
    assert len(findings) >= 1
    first = findings[0]
    assert "attack_scenario" in first
    assert "explanation" in first


async def test_orchestrator_persist_fixes_writes_fix_rows():
    gate = MagicMock()
    orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")

    fixes = [{
        "id": str(uuid4()),
        "finding_id": str(uuid4()),
        "diff": "--- a/app.py\n+++ b/app.py\n@@ -5 +5 @@\n-bad\n+good\n",
        "test": None,
        "explanation": "Fixed SQL injection.",
        "validation_result": None,
        "status": "proposed",
        "reviewer": None,
        "audit_ref": None,
    }]

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    await orch._persist_fixes(fixes, session)

    from core.db.tables import FixRow
    added_types = [type(call.args[0]).__name__ for call in session.add.call_args_list]
    assert "FixRow" in added_types


async def test_orchestrator_collect_fixes_reads_fix_generation_state():
    gate = MagicMock()
    from core.agents.base import AgentOutput
    orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")

    fix_id = str(uuid4())
    state = {
        "fix_generation": AgentOutput(
            agent_id="fix_generation",
            data={"fixes": [{"id": fix_id, "diff": "...", "explanation": "fixed"}]},
            cost_usd=0.01,
        )
    }
    result = orch._collect_fixes(state)
    assert len(result) == 1
    assert result[0]["id"] == fix_id


async def test_orchestrator_fix_agent_registered():
    gate = MagicMock()
    from core.agents.orchestrator import _AGENT_REGISTRY
    from core.agents.fix import FixAgent
    assert "FixAgent" in _AGENT_REGISTRY
    assert _AGENT_REGISTRY["FixAgent"] is FixAgent
