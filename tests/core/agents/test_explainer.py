from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from core.agents.explainer import ExplainerAgent
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode, ModelTier
from core.governance.gate import GateResult, GovernanceGate


MOCK_EXPLANATION = (
    "An attacker can send a crafted username like ' OR '1'='1 to bypass authentication "
    "or dump the entire users table. The query is built by string interpolation at app.py:5, "
    "where `username` flows directly from the HTTP request with no sanitization. "
    "Fix: use parameterized queries — conn.execute('SELECT * FROM users WHERE username = ?', (username,))."
)


@pytest.fixture
def mock_gate():
    gate = MagicMock(spec=GovernanceGate)
    gate.complete = AsyncMock(return_value=GateResult(
        content=f'{{"explanations": [{{"dedup_key": "semgrep:python.injection.sql:app.py:5", "explanation": "{MOCK_EXPLANATION}"}}]}}',
        tokens_in=400, tokens_out=150, cache_hit=False,
        model_id="claude-haiku-4-5-20251001", provider="anthropic",
        tier=ModelTier.fast, cost_usd=0.001,
    ))
    return gate


@pytest.fixture
def ctx(mock_gate):
    scan = Scan(target_ref="tests/fixtures/vulnerable_python",
                pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    triaged = [{
        "id": str(uuid4()), "scan_id": str(uuid4()),
        "rule_id": "python.injection.sql", "source_tool": "semgrep",
        "severity": "high", "cwe": "CWE-89", "owasp_category": "A03:2021",
        "dedup_key": "semgrep:python.injection.sql:app.py:5",
        "location": {"file": "app.py", "line_start": 5, "line_end": 6, "snippet": "query = f\"...\""},
        "confidence": 0.92, "exploit_likelihood": 0.85,
        "reachability": "reachable from HTTP",
        "attack_scenario": "Attacker sends crafted username to dump users table.",
        "priority_score": 9.2, "status": "open",
    }]
    return AgentContext(
        scan=scan, skills=[], budget_slice_usd=0.5, gate=mock_gate,
        extra={"triaged_findings": triaged},
    )


async def test_explainer_adds_explanation(ctx):
    agent = ExplainerAgent()
    result = await agent.run(ctx)
    explained = result.data["explained_findings"]
    assert len(explained) == 1
    assert "explanation" in explained[0]
    assert len(explained[0]["explanation"]) > 50


async def test_explainer_skips_dismissed(ctx):
    ctx.extra["triaged_findings"][0]["status"] = "dismissed"
    agent = ExplainerAgent()
    result = await agent.run(ctx)
    explained = result.data["explained_findings"]
    # dismissed findings pass through without LLM call
    assert explained[0].get("explanation") is None or explained[0].get("explanation") == ""
