from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from core.agents.triage import TriageAgent
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode, Finding, Severity, Location
from core.governance.gate import GateResult, GovernanceGate
from core.model.entities import ModelTier


def _make_finding(scan_id, severity=Severity.high, rule_id="python.injection.sql"):
    return Finding(
        scan_id=scan_id,
        rule_id=rule_id,
        source_tool="semgrep",
        severity=severity,
        cwe="CWE-89",
        owasp_category="A03:2021",
        location=Location(file="app.py", line_start=5, line_end=6,
                          snippet="query = f\"SELECT * FROM users WHERE username = '{username}'\""),
        dedup_key=f"semgrep:{rule_id}:app.py:5",
    )


@pytest.fixture
def mock_gate():
    gate = MagicMock(spec=GovernanceGate)
    gate.complete = AsyncMock(return_value=GateResult(
        content='''{
            "findings": [{
                "dedup_key": "semgrep:python.injection.sql:app.py:5",
                "confidence": 0.92,
                "exploit_likelihood": 0.85,
                "reachability": "reachable — username flows from HTTP request parameter",
                "attack_scenario": "An attacker sends a crafted username like OR 1=1 to dump the users table or bypass authentication.",
                "priority_score": 9.2,
                "status": "open",
                "false_positive_reason": null
            }]
        }''',
        tokens_in=800, tokens_out=200, cache_hit=False,
        model_id="claude-sonnet-4-6", provider="anthropic",
        tier=ModelTier.balanced, cost_usd=0.006,
    ))
    return gate


@pytest.fixture
def ctx(mock_gate):
    scan_id = uuid4()
    scan = Scan(target_ref="tests/fixtures/vulnerable_python",
                pipeline_config_id=uuid4(), mode=ScanMode.at_rest, id=scan_id)
    finding = _make_finding(scan_id)
    from core.understanding.context import CodeContext
    cc = CodeContext(root="tests/fixtures/vulnerable_python", languages={"python": 1},
                     frameworks=[], file_count=1, repo_map="app.py", entry_points=["app.py"])
    return AgentContext(
        scan=scan, skills=[], budget_slice_usd=2.0, gate=mock_gate,
        extra={"findings": [finding.model_dump(mode="json")], "code_context": cc.model_dump()},
    )


async def test_triage_enriches_findings(ctx):
    agent = TriageAgent()
    result = await agent.run(ctx)
    triaged = result.data["triaged_findings"]
    assert len(triaged) == 1
    f = triaged[0]
    assert f["confidence"] == pytest.approx(0.92)
    assert f["exploit_likelihood"] == pytest.approx(0.85)
    assert "attacker" in f["attack_scenario"].lower() or "1=1" in f["attack_scenario"]
    assert f["priority_score"] >= 9.0
    assert f["status"] == "open"


def test_approach_changes_triage_prompt():
    from core.model.entities import SecurityApproach
    from core.agents.prompts.approaches import get_triage_system
    pentest = get_triage_system(SecurityApproach.penetration_testing)
    blue = get_triage_system(SecurityApproach.blue_team)
    assert pentest != blue
    assert "attacker" in pentest.lower() or "exploit" in pentest.lower()
    assert "detect" in blue.lower() or "harden" in blue.lower()


def test_all_approaches_have_prompts():
    from core.model.entities import SecurityApproach
    from core.agents.prompts.approaches import get_triage_system
    for approach in SecurityApproach:
        prompt = get_triage_system(approach)
        assert len(prompt) > 100, f"Prompt for {approach} is too short"


async def test_triage_deduplicates(ctx):
    # duplicate finding should only appear once
    findings = ctx.extra["findings"] * 2  # same dedup_key twice
    ctx.extra["findings"] = findings
    agent = TriageAgent()
    result = await agent.run(ctx)
    keys = [f["dedup_key"] for f in result.data["triaged_findings"]]
    assert len(keys) == len(set(keys))
