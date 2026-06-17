# tests/core/governance/test_gate.py
from __future__ import annotations
import pytest
import httpx
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from core.governance.gate import GovernanceGate, GateResult
from core.governance.budget import BudgetExceeded
from core.model.entities import ModelTier


@pytest.fixture
def gate():
    return GovernanceGate(
        router_config="config/model_tiers.yaml",
        budget_config="config/budget_policy.yaml",
        gateway_url="http://localhost:3001",
    )


async def test_complete_returns_gate_result(gate, respx_mock):
    scan_id = uuid4()
    respx_mock.post("http://localhost:3001/chat").mock(
        return_value=httpx.Response(200, json={
            "content": "This is a SQL injection vulnerability.",
            "usage": {
                "tokens_in": 500,
                "tokens_out": 100,
                "cache_hit": False,
                "cost_usd": 0.0025,
                "model_id": "claude-sonnet-4-6",
                "provider": "anthropic",
            }
        })
    )
    result = await gate.complete(
        task_type="explanation",
        messages=[{"role": "user", "content": "Explain this finding."}],
        agent_id="explainer",
        scan_id=scan_id,
    )
    assert isinstance(result, GateResult)
    assert result.content == "This is a SQL injection vulnerability."
    assert result.tokens_in == 500
    assert result.cost_usd == 0.0025


async def test_budget_exceeded_raises(gate, respx_mock):
    scan_id = uuid4()
    # Pre-load budget to near limit
    gate._budget.record(scan_id, 4.99)
    respx_mock.post("http://localhost:3001/chat").mock(
        return_value=httpx.Response(200, json={
            "content": "x",
            "usage": {"tokens_in": 100, "tokens_out": 20, "cache_hit": False,
                      "cost_usd": 0.10, "model_id": "claude-sonnet-4-6", "provider": "anthropic"}
        })
    )
    with pytest.raises(BudgetExceeded):
        await gate.complete(
            task_type="triage",
            messages=[{"role": "user", "content": "triage"}],
            agent_id="triage",
            scan_id=scan_id,
        )
