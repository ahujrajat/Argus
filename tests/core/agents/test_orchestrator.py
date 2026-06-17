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
